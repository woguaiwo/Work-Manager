import os
base_dir = os.path.dirname(os.path.abspath(__file__))
marker = os.path.join(base_dir, '.shortcut_created')
with open('test_marker_result.txt', 'w', encoding='utf-8') as f:
    f.write('exists=' + str(os.path.exists(marker)) + '\n')
    f.write('marker=' + marker + '\n')
    f.write('base_dir=' + base_dir + '\n')
