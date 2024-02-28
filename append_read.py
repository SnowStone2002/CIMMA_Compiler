def add_read_n_lines_before(filename, n, append_content):
    lines = []
    with open(filename, 'rb') as file:
        file.seek(0, 2)
        bytes_in_line = file.tell()
        while bytes_in_line and len(lines) < n+1:#delete one more
            bytes_in_line -= 1
            file.seek(bytes_in_line)
            if file.read(1) == b'\n':
                line = file.readline().decode().rstrip()
                lines.insert(0, line)
    
    new_end_position = bytes_in_line + 1
    with open(filename, 'ab') as file:
        file.truncate(new_end_position)

    with open(filename, 'a') as file:
        file.write(lines[0] + " ")
        file.write(append_content)
        for line in lines[1:]:
            file.write(line + '\n')