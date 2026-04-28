import os
import argparse
import shutil
import py_compile
import json
import re
import logging
import sys
from datetime import datetime

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("sql_wrapper.log", encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger("sql_wrapper")

def is_sql_line(line):
    sql_keywords = {
        'CREATE', 'INSERT', 'SELECT', 'UPDATE', 'DELETE', 
        'WITH', 'DROP', 'ALTER', 'TRUNCATE', 'REPLACE',
        'GRANT', 'REVOKE', 'BEGIN', 'COMMIT', 'ROLLBACK'
    }
    # Clean line for keyword check
    clean = line.strip().upper()
    if not clean:
        return False
    # Check if the first word is a keyword
    first_word = clean.split()[0] if clean.split() else ""
    return first_word in sql_keywords

def strip_comments_and_blanks(content):
    """
    Strips leading blank lines and comments (#, \"\"\", ''') 
    to find the actual start of code/SQL.
    """
    lines = content.splitlines()
    start_idx = 0
    in_block_comment = False
    block_char = None
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        if not stripped:
            continue
            
        if in_block_comment:
            if block_char and stripped.endswith(block_char):
                in_block_comment = False
            continue
            
        if stripped.startswith('#'):
            continue
            
        if stripped.startswith('"""'):
            if not stripped.endswith('"""') or len(stripped) == 3:
                in_block_comment = True
                block_char = '"""'
            continue
            
        if stripped.startswith("'''"):
            if not stripped.endswith("'''") or len(stripped) == 3:
                in_block_comment = True
                block_char = "'''"
            continue
            
        # If we reach here, it's not a blank line or a comment
        start_idx = i
        break
    else:
        # Reached end without finding anything
        return "", -1

    return lines[start_idx], start_idx

def wrap_sql(content):
    """
    Splits content by ';' and wraps each block into query_1, query_2, etc.
    """
    # Simple split by semicolon. Note: This might be too simple if 
    # semicolons are inside strings, but for raw SQL files it's usually fine.
    # A more robust regex would handle quoted strings.
    blocks = [b.strip() for b in content.split(';') if b.strip()]
    
    if not blocks:
        return content
        
    wrapped_lines = []
    for i, block in enumerate(blocks, 1):
        var_name = f"query_{i}"
        wrapped_lines.append(f'{var_name} = """\n{block};\n"""')
    
    return "\n\n".join(wrapped_lines) + "\n"

def process_file(file_path, dry_run, logger):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            
        if not content.strip():
            return "skipped_empty"
            
        first_line, _ = strip_comments_and_blanks(content)
        
        if not is_sql_line(first_line):
            return "skipped_not_sql"
            
        logger.info(f"Detected SQL in: {file_path}")
        
        if dry_run:
            logger.info(f"[DRY-RUN] Would modify {file_path}")
            return "modified_dry"

        # Backup
        bak_path = file_path + ".bak"
        shutil.copy2(file_path, bak_path)
        
        # Transform
        new_content = wrap_sql(content)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        # Validate
        try:
            py_compile.compile(file_path, doraise=True)
            os.remove(bak_path)
            logger.info(f"Successfully wrapped and validated: {file_path}")
            return "modified"
        except Exception as e:
            logger.error(f"Validation failed for {file_path}: {e}. Rolling back.")
            shutil.move(bak_path, file_path)
            return "failed_rollback"
            
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        return "error"

def main():
    parser = argparse.ArgumentParser(description="Wrap raw SQL in Python triple-quotes.")
    parser.add_argument("--path", default=".", help="Directory to scan")
    parser.add_argument("--dry-run", action="store_true", help="Don't modify files")
    args = parser.parse_args()

    logger = setup_logging()
    logger.info(f"Starting SQL Wrapper scan in: {os.path.abspath(args.path)}")
    if args.dry_run:
        logger.info("DRY RUN ENABLED - No changes will be made.")

    # 1. Startup Cleanup
    bak_files = []
    for root, _, files in os.walk(args.path):
        for f in files:
            if f.endswith(".bak"):
                bak_files.append(os.path.join(root, f))
    
    if bak_files:
        logger.warning(f"Found {len(bak_files)} orphaned .bak files.")
        for b in bak_files:
            logger.info(f"Found: {b}")
        
        choice = input("Clean up existing .bak files before starting? (y/n): ").strip().lower()
        if choice == 'y':
            for b in bak_files:
                os.remove(b)
            logger.info("Cleaned up .bak files.")
        else:
            logger.info("Proceeding with existing .bak files present.")

    # 2. Main Scan
    summary = {
        "scanned": 0,
        "modified": 0,
        "skipped_not_sql": 0,
        "skipped_empty": 0,
        "failed_rollback": 0,
        "error": 0,
        "timestamp": datetime.now().isoformat()
    }

    for root, _, files in os.walk(args.path):
        # Avoid .venv, .git, etc.
        if any(ignored in root for ignored in [".venv", ".git", "__pycache__", ".clipmind_runtime"]):
            continue
            
        for f in files:
            if f.endswith(".py") and f != "sql_wrapper.py":
                summary["scanned"] += 1
                file_path = os.path.join(root, f)
                result = process_file(file_path, args.dry_run, logger)
                
                if result == "modified" or result == "modified_dry":
                    summary["modified"] += 1
                elif result in summary:
                    summary[result] += 1
                else:
                    summary["error"] += 1

    # 3. Final Report
    with open("sql_wrapper_summary.json", "w") as sf:
        json.dump(summary, sf, indent=4)
    
    logger.info("--- Scan Complete ---")
    logger.info(f"Scanned: {summary['scanned']}")
    logger.info(f"Modified: {summary['modified']}")
    logger.info(f"Failed/Rolled back: {summary['failed_rollback']}")
    logger.info(f"Errors: {summary['error']}")
    logger.info("Summary saved to sql_wrapper_summary.json")

if __name__ == "__main__":
    main()
