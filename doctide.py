# Build in python
from typing import NamedTuple
from uuid import uuid4
import sys
import os
import csv

# External dependencies
import git #gitPython
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate

# Internal dependencies
from utils.code_diff_utils import extract_data, collect_code_comment_range, tree_sitter_parser_init, detect_language

# Global vars to keep track of success rate
generation_attempts = 0
successful_generation_attempts = 0

def main(testing):

    repo = git.Repo(".")

    # Creates a branch
    branch_id = uuid4()
    branch_name = "Update-docs-" + str(branch_id)
    repo.git.branch(branch_name)
    repo.git.checkout(branch_name)


    # Set the branch name in the GitHub Actions environment
    with open(os.getenv('GITHUB_ENV'), "a") as env_file:
        env_file.write(f"BRANCH_NAME={branch_name}\n")

    head_commit = repo.head.commit

    # The modified files of the diff between HEAD and HEAD~1
    diff_files = list(head_commit.diff("HEAD~1"))

    # For each changed file, generate and insert new comments
    for file in diff_files:
        source_path = str(file.a_path)
        print("Generating comments for diffs in" + source_path)
        file_language = detect_language(source_path)
        # If not supported file language, skip file.
        if not file_language:
                continue
        prev_content = ""
        # Fetch content of file in prev commit, if file doesn't exist in prev commit, continue with ""
        try:
            prev_commit = repo.commit("HEAD~1")
            prev_blob = prev_commit.tree / source_path
            prev_content = prev_blob.data_stream.read().decode("utf-8")
        except KeyError as e:
            print(f"Head commit has a new file: {source_path}")

        # Read content of file on head commit
        with open(source_path, "r") as f:
            source_code = f.read()
        
        generatedComment_lst: list[GeneratedComment] = []
        generate_comments(file_language, prev_content, source_code, generatedComment_lst)

        # Init commented_code with original content from file
        commented_code = bytearray(source_code.encode("utf-8"))
        # Insert generated comments
        for comment, start_byte, end_byte, start_col in reversed(generatedComment_lst):
            indentation = b" " * start_col
            commented_code[start_byte:end_byte] = (comment.encode()+b"\n"+indentation)

        # Write back to file
        with open(source_path, "w") as f:
            f.write(commented_code.decode("utf-8"))

        # Add changes
        add_files = [source_path]
        repo.index.add(add_files)

    # For testing purpose
    if testing:
        success_rate_file = os.path.join("success_rate.csv")
        success_rate_file_exists = os.path.exists(success_rate_file)
        with open(success_rate_file, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not success_rate_file_exists:
                writer.writerow(["Successful runs", "Total runs"])
            writer.writerow([successful_generation_attempts, generation_attempts])

    repo.index.add(success_rate_file)

    # Commit changes
    repo.index.commit(f"Updated function-level documentation for commit: ${head_commit.hexsha}")

    repo.remotes.origin.push(refspec=f"{branch_name}:{branch_name}",set_upstream=True)

    repo.__del__()
    exit(0)

def validate_response_as_comment(language, response):
    """
    Validates whether a given `response` can be interpreted as a comment in the specified `language`.
    To ensure that no executable code created, which could lead to possible code injection, if not spotted
    in the Pull Request.

    This function parses the response using a Tree-sitter parser and checks:
    - If the parsed tree consists of a single node:
        - It must be a comment (`comment` or `block_comment`), or
        - An expression statement containing a properly enclosed string literal (triple-quoted).
    - If there are multiple nodes:
        - Every node must either be a comment or a block comment to be considered valid.

    Args:
        language: The programming language to be used by the Tree-sitter parser.
        response (str): The response text to validate.

    Returns:
        bool: True if the response is valid as a comment, False otherwise.
    """
    root = tree_sitter_parser_init(language, response.encode("utf-8"))
    children = root.children
    children_len = len(children)
    if children_len == 1:
        child = children[0]    
        return child.type in ["comment", "block_comment"] or (child.type == "expression_statement" and child.children[0].type == "string" and ((child.children[0].text.startswith(b'"""') and child.children[0].text.endswith(b'"""')) or (child.children[0].text.startswith(b"'''") and child.children[0].text.endswith(b"'''"))))
    else: 
        # All children must be comments or block_comments
        return all(child.type in ["comment", "block_comment"] for child in children)


def generate_llm_response(file_language, code):
    """
    Generate a function-level documentation comment for a given code snippet using an LLM.

    Args:
        file_language (str): The programming language of the code (e.g., 'Python', 'JavaScript').
        code (str): The source code of the function for which documentation should be generated.

    Returns:
        str: The generated documentation comment produced by the LLM.
    """

    # Create prompt for LLM
    prompt = ChatPromptTemplate.from_template(
        """
        You are a documentation assistant.

        ## Instructions:
        - Write a function-level documentation for the provided function, following best documentation practice for {program_language}
        Return **only** the comment

        ## Code:
        {code}
        """
    )

    prompt_input = prompt.format(
        code = code,
        program_language = file_language,
    )

    # Execute prompt on llm.
    llm = ChatOllama(model="llama3.2", temperature=0.0)
    llm_response = llm.invoke(prompt_input)
    return llm_response
    
class GeneratedComment(NamedTuple):
    comment: str
    start_byte: int
    end_byte: int
    start_col: int
    

def generate_comments(file_language: str, prev_content: str, source_code: str, generatedComments: list[GeneratedComment]):
    """
    Generate review comments for modified functions in a code diff.

    Extracts modified functions from the diff between previous and current content,
    generates LLM-based comments, validates them, and stores valid comments.

    Args:
        file_language (str): Programming language of the source file.
        prev_content (str): File content from the previous commit.
        source_code (str): Current file content.
        generatedComments (list of GeneratedComment): List to append valid generated comments.
        
    Returns:
        None
    """
    # Testing variables
    global generation_attempts, successful_generation_attempts
    
    # Extract all functions which is in the diff
    functions = extract_data(True, file_language, prev_content, source_code, collect_code_comment_range)

    # Generate new comments for modified functions
    for function_code, start_byte, end_byte in functions:
        generation_attempts += 1
        llm_response = generate_llm_response(file_language, function_code)
        if validate_response_as_comment(file_language, llm_response.content):
            successful_generation_attempts += 1
            generatedComments.append(GeneratedComment(comment=llm_response.content, start_byte=start_byte, end_byte=end_byte))


if __name__ == "__main__":
    testing = False
    testing = sys.argv[1]
    main(testing)

