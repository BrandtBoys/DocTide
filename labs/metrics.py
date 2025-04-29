# Build in python
import csv

# External dependencies
from sentence_transformers import CrossEncoder

# Internal dependencies
from utils.code_diff_utils import extract_data, collect_code_comment_pairs, detect_language, get_agent_diff_content

def collect_semantic_score(repo, branch_name, modified_files, commit_sha, result_file):
    #fetch the latest changes to the test branch
    branch = repo.get_branch(branch_name)
    #fetch the HEAD commit of test branch
    agent_HEAD_commit = branch.commit.sha

    result_rows = []
    comment_pairs = []
    comment_metedata = []

    for filename in modified_files:
        file_language = detect_language(filename) 
        if not file_language:
            continue
        original_content = repo.get_contents(filename,ref=commit_sha).decoded_content.decode() # original commit
        # Find the original pairs of comments which relates to some code
        original_comment_code_pairs = extract_data(False, file_language, None, original_content,collect_code_comment_pairs)

        # Find pairs of comments which the agent has made to some code
        agent_comment_code_pairs = get_agent_diff_content(repo, filename, agent_HEAD_commit, file_language)

        # collects pairs of comments_code_pairs from original and agent, where the code is 
        # identical and save the comments if the comments differs (Where the agent has made a change)
        for agComment, agCode in agent_comment_code_pairs:
            for orgComment, orgCode in original_comment_code_pairs:
                if orgCode.strip() == agCode.strip() and orgComment.strip() != agComment.strip():
                    comment_pairs.append([orgComment, agComment])
                    comment_metedata.append([orgCode, filename, agent_HEAD_commit])

    if not comment_pairs:
        return

    scores = calculate_semantic_scores(comment_pairs)

    for score, (orgComment, agComment), (code, filename, commit) in zip(scores, comment_pairs, comment_metedata):
        result_rows.append([score, code, orgComment, agComment, filename, commit])

    with open(result_file, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(result_rows)

def calculate_semantic_scores(commentPairs):
    model = CrossEncoder("cross-encoder/stsb-roberta-base")
    scores = model.predict(commentPairs)
    return scores
