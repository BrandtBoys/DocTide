# Build in python
import re
import os

# External dependencies
import difflib
from tree_sitter import Parser
from tree_sitter_languages import get_language


class CommentNode:
    '''A class to enable merging leading comments into one object'''
    def __init__(self, nodes):
        self.nodes = nodes
        self.start_byte = nodes[0].start_byte
        self.end_byte = nodes[-1].end_byte
        self.start_point = (nodes[0].start_point[0]+1,nodes[0].start_point[1])
        self.end_point = (nodes[-1].end_point[0]+1,nodes[-1].end_point[1]+1)

    def __repr__(self):
        return f"<CommentNode comment>\n{self.content}"


def extract_data(use_diff, file_language, head_content, commit_content, handler_fn, build_tree_from_head_content = False):
    """
    Extract data from parsed source code using Tree-sitter, optionally using diff information.

    This function parses the provided source code with Tree-sitter and traverses the syntax tree
    to find function definitions. It can operate in diff-aware mode (only analyzing changed functions)
    or on the full file. For each qualifying function, a handler function is called which handles appending
    the specific wanted data to the return list.

    Parameters
    ----------
    use_diff : bool
        If True, only analyze functions that include changed lines (based on diff between head and commit).
    file_language : str
        Language identifier used to initialize the Tree-sitter parser (e.g., "python", "javascript").
    head_content : str
        The content of the file at the head (used for diffing).
    commit_content : str
        The content of the file at the commit (parsed and analyzed).
    handler_fn : function
        A callback function that takes the form:
        `handler_fn(func_node, node, content, result_list)`
        and is called for each qualifying function.
    build_tree_from_head_content : bool
        If True analyse head_content instead of commit_content

    Returns
    -------
    list
        The accumulated results collected by the `handler_fn`.
    """    
    changed_lines = []
    if use_diff:
        changed_lines = get_changed_line_numbers(head_content, commit_content, build_tree_from_head_content)
        if not changed_lines:
            return []
    
    if not build_tree_from_head_content:
        root_node = tree_sitter_parser_init(file_language,commit_content.encode("utf-8"))
    else:
        root_node = tree_sitter_parser_init(file_language,head_content.encode("utf-8"))


    result = []

    nodeId = set() # To track already visited nodes

    def traverse_functions(root_node, changed_lines, handler_fn):
        """
        Traverse the syntax tree and invoke handler_fn on qualifying function nodes.

        Parameters
        ----------
        root_node : tree_sitter.Node
            The root of the parsed syntax tree.
        changed_lines : list[int]
            List of changed line numbers (if diff is used).
        handler_fn : function
            A function which handles what kind of data to extract.
        """
        def visit(node):
            if node.id in nodeId:
                return
            else:
                nodeId.add(node.id)
                try:
                    if node.type == "function_definition":
                        start_line = node.start_point[0] + 1
                        end_line = node.end_point[0] + 1
                        line_range = range(start_line, end_line + 1)
                        if any(line in changed_lines for line in line_range) or not use_diff:
                            if file_language == "python":
                                block_node = next((child for child in node.children if child.type == "block"), None)
                                if not block_node or not block_node.children:
                                    raise Exception("No block or block has no children in function")

                                expected_comment_node = block_node.children[0]
                                
                                handler_fn(func_node=node, node=expected_comment_node, content=commit_content, nodeIdSet=nodeId, result_list=result, mod_lines=set(changed_lines).intersection(line_range), file_language=file_language)
                            else:
                                print("language not supported")
                            
                except Exception as e:
                    print(f"error: {e}")
                for child in node.children:
                    visit(child)

        visit(root_node)
    traverse_functions(root_node, changed_lines, handler_fn)
    return result 

# ----------------vvvvv HANDLER FUNCTIONS vvvvv----------------
        
# Handler function to extrat data
#Used in remove_comments
def collect_comment_range(node, result_list, nodeIdSet, **kwargs):
    '''
    Asses if a node is a comment node, and appends tuples with the comment nodes start_byte and end_byte to the result_list

        Parameter:
            tree_sitter.Node
            List[Tuple[int,int]]

    '''
    comment_node = identify_comment_node(node, nodeIdSet)
    if comment_node :
        start_byte = comment_node.start_byte
        end_byte = comment_node.end_byte
        result_list.append((start_byte,end_byte))

def collect_comment_lines(node, result_list, nodeIdSet, **kwargs):
    '''
    Asses if a node is a comment node, and appends tuples with the comment nodes start_byte and end_byte to the result_list

        Parameter:
            tree_sitter.Node
            List[Tuple[int,int]]

    '''
    comment_node = identify_comment_node(node, nodeIdSet)
    if comment_node :
        for line in range(comment_node.start_point[0], comment_node.end_point[0]+1):
            result_list.append(line)

# Handler function to extrat data
# Used in agent
def collect_code_comment_range(func_node, node, content, result_list, nodeIdSet, file_language, **kwargs):
    """
    Extracts the source code of a function and any associated comment,
    then appends this data along with byte range information to the result list.

    If no comment is found, an empty string is used for the comment, and the byte
    range is set to the start of the function block.

    Parameters:
        func_node (tree_sitter.Node): The syntax node representing the function.
        node (tree_sitter.Node): The first node in function block, possibly a comment or string.
        content (str): The full source code text.
        result_list (List[Tuple[str, str, int, int]]): A list to which the tuple
            (function source code, start byte, end byte) will be appended.

    Returns:
        None
    """
    function_code = content[func_node.start_byte : func_node.end_byte].strip()
    if file_language == "python":
        # --- specific for python: detect prev function level comment placement (after function definition)---
        last_node_before_block = node.parent.prev_sibling 
        _ , start_col = func_node.start_point
        start_row, _ = last_node_before_block.end_point
        # Calculating the start_point to right under and one index in from the func def.
        start_row = start_row
        start_col = start_col+4
        start_byte = point_to_byte(content.encode("utf-8"),start_row,start_col)
        end_byte = start_byte
    else:
        # To make DocTide work for other languages, place logic to to extract
        # appropriate function level comment placement here (E.g. java, js, c# 
        # should be above the func def)
        print("language not supported")
        return
    comment_node = identify_comment_node(node, nodeIdSet)
    if comment_node:
        end_byte = comment_node.end_byte
    result_list.append((function_code, start_byte, end_byte, start_col))

# Handler function to extrat data
# Used in semantic
def collect_code_comment_pairs(func_node, node, content, result_list, nodeIdSet, **kwargs):
    """
    Appends a record containing the source code of a function and its associated comment
    to the result_list, if a valid comment is found at start of function block.

    The comment must be of type 'comment', 'block_comment', or a string literal node.

    Parameters:
        func_node (tree_sitter.Node): The syntax node representing the function.
        node (tree_sitter.Node): The first node in function block, potentially a comment or string.
        content (str): The full source code as a string.
        result_list (List[Tuple[str, str]]): A list to which the tuple
            (function source code, associated comment) will be appended.

    Returns:
        None
    """
    func_def = " ".join(child.text.decode("utf-8") for child in func_node.children[:2])
    code = func_def
    old_comment = ""
    comment_node = identify_comment_node(node, nodeIdSet)
    if comment_node:
        old_comment = content[comment_node.start_byte: comment_node.end_byte]
        result_list.append((old_comment, code))

# Handler function to extrat data
def collect_comment_change_lines(node, nodeIdSet, mod_lines, result_list, **kwargs):
    """
    Collect modified line numbers that overlap with a comment node.

    Checks if any modified lines fall within the range of a detected comment node,
    and appends those line numbers to the result list.

    Args:
        node: The syntax tree node to inspect.
        nodeIdSet (set): A set of node IDs used to identify comment nodes.
        mod_lines (iterable): A collection of modified line numbers to check.
        result_list (list): The list to append matching line numbers to.
        **kwargs: Additional keyword arguments (currently unused).

    Returns:
        None
    """
    node.end_point[0]
    comment_node = identify_comment_node(node, nodeIdSet)
    if comment_node:
        for line in mod_lines:
            if line in range(comment_node.start_point[0],comment_node.end_point[0]+1):
                result_list.append(line)

# ----------------vvvvv HELPER FUNCTIONS vvvvv----------------

# Helper function
def get_changed_line_numbers( head_content, commit_content, count_on_head_commit):
    """
    Identify changed line numbers between two versions of file content.

    Compares head content and commit content using a unified diff to find
    which lines were added, removed, or modified, depending on the counting mode.

    Args:
        head_content (str): The content from the head commit (current version).
        commit_content (str): The content from the commit (incoming version).
        count_on_head_commit (bool): If False, count line numbers based on the incoming commit;
                                     if True, count based on the head commit.

    Returns:
        set: A set of integers representing the changed line numbers.
    """
    changed_lines = set()
    if head_content:

        diff = list(difflib.unified_diff(
        head_content.splitlines(), commit_content.splitlines(), n=0
        ))

        new_line_num = 0
        for line in diff:
            if line.startswith('@@'):
            # Handles offset given by meta data
                match = re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
                if match:
                    if not count_on_head_commit:
                        new_line_num = int(match.group(3)) - 1
                    else:
                        new_line_num = int(match.group(1)) - 1
            elif line.startswith('+') and not line.startswith('+++'):
                if not count_on_head_commit:
                    new_line_num += 1
                    changed_lines.add(new_line_num)
                else:
                    continue
            elif line.startswith('-') and not line.startswith('---'):
                if not count_on_head_commit:
                    continue  # don't increment line number
                else: 
                    new_line_num += 1
                    changed_lines.add(new_line_num)
            else:
                new_line_num += 1  # context line
    # The case of a new file (content only exist in incoming commit), all lines are added
    elif not head_content and not count_on_head_commit:
        counter = 1
        for line in commit_content.splitlines():
            changed_lines.add(counter)
            counter += 1
    return changed_lines

# Helper function
def identify_comment_node(node, nodeIdSet):
    """
    Identify and return a CommentNode if the given node represents a comment or a group of leading comment nodes.

    This function inspects the given node and determines whether it is a comment-related node.
    - If the node is a line comment, it will attempt to collect consecutive leading comments
      (at the top of its parent block) and merge them into a single CommentNode.
    - If the node is a block comment or starts with a string (e.g., Python-style docstrings), it is wrapped directly.

    Parameters
    ----------
    node : tree_sitter.Node
        The Tree-sitter node to inspect.
    nodeIdSet : set
        A set used to track the IDs of processed comment nodes (to avoid reprocessing).

    Returns
    -------
    CommentNode or None
        A CommentNode object if the input node is a recognized comment type,
        otherwise None.
    """
    if node.type == "comment":
        # merge leading comments
        block_node = node.parent
        comment_nodes = []
        for child in block_node.children:
            if child.type == "comment":
                comment_nodes.append(child)
                nodeIdSet.add(child.id)
            else:
                break  # Stop when the first non-comment node is reached

        if comment_nodes:
            return CommentNode(comment_nodes)
        return None
    elif node.type == "block_comment" or \
       (node.children and node.children[0].type == "string"):
        return CommentNode([node])
    else:
        return None

#Helper function
def tree_sitter_parser_init(file_language, content):
    parser = Parser()
    language = get_language(file_language)
    parser.set_language(language)
    tree = parser.parse(content)
    root_node = tree.root_node
    return root_node

#Helper function
def point_to_byte(source: bytes, row: int, col: int) -> int:
    '''
    Converts points(row,col) to bytes-offset based on a given source (str)
    '''
    lines = source.splitlines(keepends=True)
    byte_offset = sum(len(lines[i]) for i in range(row+1)) + col
    return byte_offset

#Helper function
def edit_diff_restore_comments(file_language, head_content, cleaned_content):
    """
    Restore removed comment lines in a cleaned file diff based on modified comment lines.

    Compares the original head content and cleaned content to detect comment lines that were
    incorrectly removed, and reconstructs a corrected file version preserving those comments.

    Args:
        file_language (str): The programming language of the source file.
        head_content (str): The original content of the file before cleaning.
        cleaned_content (str): The cleaned content of the file after modifications.

    Returns:
        str: The reconstructed file content with restored comments.
    """
    mod_comment_lines = set(extract_data(True, file_language,head_content, cleaned_content, collect_comment_change_lines, build_tree_from_head_content=True))
    diff = difflib.ndiff(head_content.splitlines(), cleaned_content.splitlines())
    diff_list = list(diff)
    
    counter = 1
    mod_diff = [] 
    for line in diff_list:
        if counter in mod_comment_lines and line.startswith("-"):
            mod_diff.append(" " + line[1:])
        elif line.startswith(" "):
            mod_diff.append(line)
        elif line.startswith("+") or line.startswith("?"):
            mod_diff.append(line)
            continue
        counter = counter + 1 
    
    modified_file = difflib.restore(mod_diff, 2)
    modified_file_str = "\n".join(modified_file)

    return modified_file_str

# Used in doctide_labs
def remove_diff_comments(file_language, head_content, commit_content):
    """
    Remove comments from functions that were changed in a commit diff.

    This function uses Tree-sitter to identify comments within function definitions that are
    affected by a code diff (between `head_content` and `commit_content`). It then removes
    those specific comment byte ranges from the `commit_content`.

    Parameters
    ----------
    file_language : str
        The programming language of the file (e.g., "python", "javascript") used to initialize the Tree-sitter parser.
    head_content : str
        The content of the file in the base (head) revision, used for diff comparison.
    commit_content : str
        The content of the file in the new (commit) revision, from which comments will be removed.

    Returns
    -------
    str
        The updated source code with targeted diff-related comments removed.
    """
  
    # Extract comment lines
    diff_comment_lines = set(extract_data(True, file_language, head_content, commit_content, collect_comment_lines))
    
    content = commit_content.splitlines(keepends=True)
    cleaned_content = []
    counter = 1
    if diff_comment_lines:
        for line in content:
            if counter not in diff_comment_lines:
                cleaned_content.append(line)
            counter += 1
    else:
        return commit_content+"\n"
    print("No comment found")
    
    return("".join(cleaned_content)+"\n")

def remove_comments(file_language, commit_content):
  
    # Extract comment lines
    diff_comment_lines = set(extract_data(use_diff=False, file_language=file_language, head_content="", commit_content=commit_content, handler_fn=collect_comment_lines))
    
    content = commit_content.splitlines(keepends=True)
    cleaned_content = []
    counter = 1
    if diff_comment_lines:
        for line in content:
            if counter not in diff_comment_lines:
                cleaned_content.append(line)
            counter += 1
    else:
        return commit_content+"\n"
    print("No comment found")
    
    return("".join(cleaned_content)+"\n")

# Helper function, used in metrics
def get_agent_diff_content(repo, filename, commit_sha, file_language):
    """
    Extract comment/code pairs from a file that changed in a specific commit using custom Tree-sitter diff analysis from the dt_diff_lib library.

    This function retrieves the content of a file before and after a given commit, computes the diff between them,
    and extracts function-level code and associated comments that were affected. It uses Tree-sitter to parse and
    analyze the changed portions of the code.

    Parameters
    ----------
    repo : github.Repository.Repository
        The GitHub repository object from the PyGithub API.
    filename : str
        The path to the file being analyzed within the repository.
    commit_sha : str
        The SHA of the commit where changes are to be analyzed.
    file_language : str
        The programming language of the file (e.g., "python", "javascript").

    Returns
    -------
    list
        A list of extracted comment/code pairs (or related structures), as returned by `collect_code_comment_pairs`.

    Notes
    -----
    - This function assumes that `collect_code_comment_pairs` is a valid handler function compatible with `extract_data`.
    - Only function definitions affected by the diff will be analyzed.
    """
    commit = repo.get_commit(sha=commit_sha)
    old_content = repo.get_contents(filename, ref=commit.parents[0].sha).decoded_content.decode() # test commit
    new_content = repo.get_contents(filename, ref=commit.sha).decoded_content.decode() # agent commit
    return extract_data(True, file_language, old_content, new_content, collect_code_comment_pairs)

# Mapping of file extensions to programming languages
EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".java": "java",
    ".js": "javascript",
    ".ts": "typescript",
    ".c": "c",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".go": "go",
    ".rs": "rust"
}

#Helper function
def detect_language(filename):
    """Detects programming language based on file extension."""
    _, ext = os.path.splitext(filename)  # Extract file extension
    return EXTENSION_TO_LANGUAGE.get(ext, None)  # Return language or "unknown"
