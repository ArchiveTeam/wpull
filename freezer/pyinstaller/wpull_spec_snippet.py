import glob

plugin_paths = glob.glob('../../wpull/application/plugins/*.py')

for path in plugin_paths:
    data_path = 'wpull/application/plugins/' + os.path.basename(path)
    print('Data path', data_path, path)
    a.datas += [(data_path, path, 'DATA')]
