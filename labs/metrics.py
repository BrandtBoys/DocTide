# Build in python
import csv
import sys
import os
import pandas as pd
import matplotlib.pyplot as plt

# External dependencies
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from sentence_transformers import CrossEncoder

# Internal dependencies
from utils.code_diff_utils import extract_data, collect_code_comment_pairs, detect_language, get_agent_diff_content

def collect_semantic_score(repo, branch_name, modified_files, commit_sha, result_file, timestamp):
    #fetch the latest changes to the test branch
    branch = repo.get_branch(branch_name)
    #fetch the HEAD commit of test branch
    agent_HEAD_commit = branch.commit.sha

    result_rows = []
    comment_pairs = []
    comment_metedata = []

    for filename,_ in modified_files:
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

def create_semantic_score_box_plot(result_file,timestamp):    
    #create a box-plot figure
    df = pd.read_csv(result_file)

    stats = df["Semantic-Score"].describe()
    q1 = stats['25%']
    median = stats['50%']
    q3 = stats['75%']
    min_val = stats['min']
    max_val = stats['max']
    count = df["Semantic-Score"].count()

    plt.figure(figsize=(8, 6))
    df["Semantic-Score"].plot.box()
    plt.title("Bot plot of semantic score")
    plt.text(1.3, df['Semantic-Score'].median(), f'n = {count}', ha='left', va='center')
    # Add annotations for Q1, Median, Q3
    plt.text(1.1, q1, f'Q1: {q1:.4f}', va='center', ha='left', fontsize=9, bbox=dict(facecolor='lightgray', edgecolor='none'))
    plt.text(1.1, median, f'Median: {median:.4f}', va='center', ha='left', fontsize=9, bbox=dict(facecolor='lightgray', edgecolor='none'))
    plt.text(1.1, q3, f'Q3: {q3:.4f}', va='center', ha='left', fontsize=9, bbox=dict(facecolor='lightgray', edgecolor='none'))

    # Add min/max as well if you like
    plt.text(1.05, min_val, f'Min: {min_val:.4f}', va='center', ha='left', fontsize=8, bbox=dict(facecolor='lightblue', edgecolor='none'))
    plt.text(1.05, max_val, f'Max: {max_val:.4f}', va='center', ha='left', fontsize=8, bbox=dict(facecolor='lightblue', edgecolor='none'))

    plt.savefig(f"results/{timestamp}/semantic_score_box_plot.png")



import pandas as pd
import ast
import os

def generate_success_report(csv_file, timestamp):
    # Load CSV
    df = pd.read_csv(
        csv_file,
        sep=',',
        quotechar="'",
        escapechar='\\',
        skipinitialspace=True,
    )

    # Ensure correct column names (strip whitespaces)
    df.columns = df.columns.str.strip()

    # Calculate success ratio
    total = len(df)
    successes = df['Success'].sum()  # Assumes True=1, False=0
    success_ratio = successes / total if total > 0 else 0

    # Filter failed comments (Success == False)
    failures_df = df[df['Success'] == False]

    # Pick 10 random failed comments
    sample_failures = failures_df['Comment'].sample(n=min(10, len(failures_df)), random_state=42).tolist()

    md_file = f"results/{timestamp}/success_report.md"

    # Make sure the directory exists
    os.makedirs(os.path.dirname(md_file), exist_ok=True)

    # Write to Markdown file
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(f"# Success Report\n\n")
        f.write(f"**Success ratio:** {success_ratio:.2%} ({successes}/{total} successful)\n\n")

        f.write(f"## Sample of 10 Failures:\n\n")
        for i, comment in enumerate(sample_failures, 1):
            f.write(f"### Failure {i}:\n")
            f.write(f"> {comment.strip()}\n\n")

    print(f"Report saved to {md_file}")



def calculate_semantic_scores(commentPairs):
    model = CrossEncoder("cross-encoder/stsb-roberta-base")
    scores = model.predict(commentPairs)
    return scores