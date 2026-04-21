"""File: fix.py
Purpose: Utility script to fix type hints in route files.
         Removes Optional type hints that were incorrectly chained.
         Run this once to clean up legacy type annotations.
"""

import os

d = 'api/routes'
for f in os.listdir(d):
    if f.endswith('.py'):
        path = os.path.join(d, f)
        with open(path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        new_content = content.replace(' | JSONResponse', '').replace(' | Response', '')
        
        if content != new_content:
            with open(path, 'w', encoding='utf-8') as file:
                file.write(new_content)
