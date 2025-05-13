from metrics import create_semantic_score_box_plot
import sys

if __name__ == "__main__":
    # result_file is the absolute path to the semantic_score file
    # timestamp is the timestamp of the folder name
    result_file = sys.argv[1]
    timestamp = sys.argv[2]
    create_semantic_score_box_plot(result_file, timestamp)
