import sys
import os

input_path = os.environ.get('mapreduce_map_input_file', 'unknown')

if '/input/' in input_path:
    filename = input_path.split('/input/', 1)[1]
else:
    filename = os.path.basename(input_path)

for line in sys.stdin:
    print(f"{filename}\t1")
