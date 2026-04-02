import sys

current_file = None
count = 0

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    filename, one = line.split('\t', 1)
    if filename == current_file:
        count += int(one)
    else:
        if current_file is not None:
            print(f'"{current_file}": {count}')
        current_file = filename
        count = int(one)

if current_file is not None:
    print(f'"{current_file}": {count}')
