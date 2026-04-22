import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.getcwd())))

from db.repositories.jobs import create_job
import inspect

print(f"create_job is from: {inspect.getfile(create_job)}")
print(f"create_job signature: {inspect.signature(create_job)}")
