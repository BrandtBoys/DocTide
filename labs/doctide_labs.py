# build in python
import os
import time
import csv
import uuid
from itertools import islice
from dotenv import load_dotenv
from datetime import datetime

# external dependencies
import github #pyGithub
from github.InputGitTreeElement import InputGitTreeElement

# internal dependencies
from metrics import collect_semantic_score
from utils.code_diff_utils import remove_diff_comments, edit_diff_restore_comments, detect_language, remove_comments


load_dotenv()

# GitHub repository details
GITHUB_OWNER = "BrandtBoys"  # Change this
REPO_NAME = "flask-fork"  # Change this
WORKFLOW_NAME = "update_docs.yml"  # Change if different
GITHUB_TOKEN = os.getenv("GITHUB_PAT")  # Use a Personal Access Token

# Generate a unique branch name
branch_name = f"test-agent-{uuid.uuid4()}"
#instantiate github auth
g = github.Github(login_or_token=GITHUB_TOKEN)
print("github")

#get repo
repo = g.get_repo(f"{GITHUB_OWNER}/{REPO_NAME}")
print("repo")

# Commits to compare (replace or allow user input)
start = 184   # what index of commit the test should start from, have to be higher than "end"
end = 180  # what index of commit the test should end at

#set of files which have been modified during the test
modified_filepaths = set()

#the list of all commits from a given branch, where index 0 is HEAD
commits = list(islice(repo.get_commits(sha="main"), end, start))
print("commits")

#Branch out to test env, from the specified commit you want to start the test from
repo.create_git_ref(ref='refs/heads/' + branch_name, sha=commits[-1].sha)
print("create branch")
branch = repo.get_branch(branch_name)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# Define the base results directory
os.makedirs("results/semantic_score", exist_ok=True)
os.makedirs("results/success_rate", exist_ok=True)
semantic_score_result_file = os.path.join("results/semantic_score", f"{timestamp}.csv")
success_rate_result_file = os.path.join("results/success_rate", f"{timestamp}.csv")
with open(semantic_score_result_file, mode="w", newline="", encoding="utf-8") as f:
    header = ["Semantic-Score", "Code", "Original-Comment","Agent-Comment", "Filename", "Agent-Commit"]
    writer = csv.writer(f)
    writer.writerow(header)

def main():
    #Remove all comments from .py
    cleaned_files = []
    tree_sha = branch.commit.sha
    tree = repo.get_git_tree(tree_sha, recursive=True).tree

    for item in tree:
        if item.type == "blob" and item.path.endswith(".py"):
            content = repo.get_contents(item.path,ref=tree_sha).decoded_content
            cleaned_content = remove_comments('python', content)
            with open(item.path, "w") as f:
                f.write(cleaned_content.decode("utf-8"))
            cleaned_files.append(item.path)

    ref = repo.get_git_ref(f'heads/{branch_name}')
    commit = repo.get_git_commit(tree_sha)
    commit_multiple_files(ref, cleaned_files, commit, "Remove all comments")


    #read the content of the test_workflow, and add it into the test environment, which enables the test 
    #repo to call DocTide workflow
    with open ("update_docs.yml", "r") as f:
        test_workflow = f.read()
        update_file(".github/workflows/update_docs.yml", test_workflow)
    
    #add loop of commits
    for commit in reversed(commits):
        print(commit)
        add_commit_run_agent(commit.sha)
    

def add_commit_run_agent(commit_sha):
    branch = repo.get_branch(branch_name)
    ref = repo.get_git_ref(f'heads/{branch_name}')
    #Get the HEAD commit of test branch
    head_commit_sha = branch.commit.sha 
    head_commit = repo.get_git_commit(head_commit_sha)
    #code diff between the HEAD commit and the next commit
    diff = repo.compare(head_commit_sha,commit_sha) 

    modified_files = []

    for file in diff.files:
        #This is to fix the meta problem of handling commits that changes update_docs
        if file.filename == ".github/workflows/update_docs.yml":
            continue
        #use helper script to detect which language the modified file is written in
        file_language = detect_language(file.filename) 
        if not file_language:
            continue
        #add the file to the set of modified files:
        modified_filepaths.add(file.filename)

        #Get the version of the modified file from the new commit
        content = repo.get_contents(file.filename,ref=commit_sha).decoded_content
        head_content = ""
        try:
            head_content = repo.get_contents(file.filename, ref= head_commit_sha).decoded_content.decode("utf-8")
        except Exception:
            print("file does not exist")
        #use helper script to remove all comments from the modified file
        cleaned_commit = remove_diff_comments(file_language, head_content, content.decode("utf-8"))

        modified_file = edit_diff_restore_comments(file_language,head_content,cleaned_commit)
        
        #add modified files to list
        modified_files.append((file.filename, modified_file))

    if commit_multiple_files(ref, modified_files, head_commit, "Add incoming files, replicated commit without comments."):
        workflow = repo.get_workflow(WORKFLOW_NAME)
        workflow.create_dispatch(ref=branch_name)
        time.sleep(5)

        # wait to see when the action is finished, before moving on.
        run = workflow.get_runs()[0]
        while run.status not in ["completed"]:
            time.sleep(5)  # Wait and check again
            run = workflow.get_runs()[0]  # Refresh latest run

    collect_semantic_score(repo, branch_name, modified_files, commit_sha, semantic_score_result_file)
    extract_success_rate_metric_from_agent()

    

def commit_multiple_files(ref, files, last_commit, commit_message):
    """
    Commit multiple files to a GitHub branch using the PyGithub API.

    This function stages and commits multiple file changes in a single Git commit,
    then moves the specified branch reference to the new commit.

    Parameters
    ----------
    ref : github.Reference
        The reference object for the branch (e.g., `repo.get_git_ref("heads/main")`).
    files : list of tuple[str, str]
        A list of tuples where each tuple contains:
        - path (str): the file path in the repo.
        - content (str): the file content to commit.
    last_commit : github.GitCommit
        The last commit object on the branch, used as the parent for the new commit.
    commit_message : str
        The commit message for the new commit.

    Returns
    -------
    bool
        True if the commit was created and the branch pointer was updated.
        False if there were no files to commit.

    Notes
    -----
    - This function assumes access to a global `repo` object (of type `github.Repository.Repository`).
    - Uses UTF-8 encoding for file content.
    """
    if not files:
        print("No file-changes to commit")
        return False
    # Create blobs for each file (this uploads the content to GitHub)
    blobs = []
    for path, content in files:
        blob = repo.create_git_blob(content, "utf-8")
        blobs.append((path, blob))

    # Create a tree that includes all files
    tree_elements = []
    for path, blob in blobs:
        tree_element = InputGitTreeElement(path=path, mode="100644", type="blob", sha=blob.sha)
        tree_elements.append(tree_element)

    new_tree = repo.create_git_tree(tree_elements, last_commit.tree)

    new_commit = repo.create_git_commit(commit_message, new_tree, [last_commit])

    #Move the branch pointer to the new commit
    ref.edit(new_commit.sha)
    return True

def update_file(file_name, content):
    """
    Update or create a file in a GitHub repository branch using the PyGithub API.

    This function checks if the specified file exists in a branch (`branch_name`). If it exists,
    the file is updated with new content. If it does not exist (404 error), the file is created.

    Parameters
    ----------
    file_name : str
        The name (or path) of the file to update or create in the repository.
    content : str
        The new content to write to the file.

    Raises
    ------
    Exception
        If an unexpected error occurs during the GitHub API call (excluding 404).
    """
    try:
        # Check if file exists in the branch
        contents = repo.get_contents(file_name, ref=branch_name)
        
        # If file exists, update it
        repo.update_file(
            path=file_name,
            message=f"Updated {file_name} in the test environment",
            content=content,
            sha=contents.sha,  # Required for updating an existing file
            branch=branch_name
        )

    except Exception as e:
        # If file doesn't exist, create it
        if "404" in str(e):  # File not found error
            repo.create_file(
                path=file_name,
                message=f"Added {file_name} to the test environment",
                content=content,
                branch=branch_name
            )
        else:
            raise  # Raise other unexpected errors

def extract_success_rate_metric_from_agent ():
    branch = repo.get_branch(branch_name)
    head_commit_sha = branch.commit.sha
    try:
        success_rate_content = repo.get_contents("success_rate.csv",ref=head_commit_sha).decoded_content.decode("utf-8")
        print(success_rate_content)
        with open(success_rate_result_file, mode="a", encoding="utf-8") as f:
            f.write(success_rate_content)
    except:
        print("No success_rate file found")

if __name__ == "__main__":
    main()