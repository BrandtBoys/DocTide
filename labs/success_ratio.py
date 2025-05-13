from metrics import generate_success_report
import sys

if __name__ == "__main__":
    result_file = sys.argv[1]
    timestamp = sys.argv[2]
    generate_success_report(result_file,timestamp)