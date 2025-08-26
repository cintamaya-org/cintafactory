
import os
import sys
from pathlib import Path

import toml

DEFAULT_GIT_COMMAND = 'git --git-dir=$HOME/.dotfiles --work-tree=$HOME'
DEFAULT_GIT_DIR = Path(os.environ.get('HOME'), '.dotfiles', '.git')
DEFAULT_WORK_TREE = Path(os.environ.get('HOME'))


def configs() -> dict:
    """Load all the configs if they exist, else return default_config"""

    if is_initialized() is False:
        print('Error! Dotfiles not initialized. Run `dot init` to initialize dotfile repository.')
        print('Exiting...')
        sys.exit()

    try:
        with open(config_file()) as cfg:
            configs = toml.load(cfg)
            return configs.get('dot')
    except toml.decoder.TomlDecodeError as e:
        print(e)
        print(f'Error reading config file {config_file()}')
        print('Exiting...')
        sys.exit()
    except Exception as e:
        print(e)
        print('An error occured. Please report an issue at https://github.com/kylepollina/dot')
        print('Exiting...')
        sys.exit()

    return configs


def is_initialized() -> bool:
    """Check if dotfile repository has been initialized"""
    if config_file().exists():
        return True
    else:
        return False


def config_file() -> Path:
    """ Return the path of the config file """
    return _dot_home() / 'config.toml'


def _dot_home() -> Path:
    """
    Returns a path pointed by the $DOT_HOME variable if exists,
    otherwise returns $HOME path
    """
    dot_home = os.environ.get('DOT_HOME')
    if dot_home is None:
        home = Path(os.environ.get('HOME'))
        default_dot_home = home / '.config' / 'dot'
        return default_dot_home
    else:
        return Path(dot_home)


def git_command() -> str:
    """Returns the full git command with correct git directory and worktree"""
    return f'git --git-dir={git_dir()} --work-tree={work_tree()}'


def git_dir() -> Path:
    """Returns the path of of the .git directory"""
    return Path(expand_path(configs().get('git-dir')))


def work_tree() -> Path:
    """Returns the path to the work tree"""
    return Path(expand_path(configs().get('work-tree')))


def _repo_path() -> Path:
    """Returns the path of the repository"""
    return git_dir().parent


def expand_path(path) -> str:
    """
    Expands a path to its full absolute path
    Ex.
        ~/Desktop -> /User/kyle/Desktop
        $HOME -> /User/kyle
    """
    expanded_path = os.path.expandvars(path)
    return os.path.expanduser(expanded_path)


def diff_filter(filter) -> list:
    """Return a list of files in the given diff filter for indexed files only"""
    tmp_file = f'{_dot_home()}/tmp.txt'
    full_command = f'{git_command()} diff --name-only --cached --diff-filter={filter} > {tmp_file}'
    os.system(full_command)
    with open(tmp_file, 'r') as tmp:
        files = tmp.readlines()
    os.remove(tmp_file)
    return [file.strip() for file in files]


def init() -> None:
    print('===== dotfile setup =====')
    print('Choose how you want to initialize your dotfiles:')
    print('[0] Create new dotfile repository')
    print('[1] Use existing dotfile repository')
    user_input = _init_user_input()

    if user_input == 'create_new_repository':
        _create_new_repository()
    elif user_input == 'use_existing_repository':
        _use_existing_repository()
    else:
        print('Exiting...')
        sys.exit()


def _init_user_input() -> str:
    user_input = input(' > ')
    if user_input == '0':
        return 'create_new_repository'
    elif user_input == '1':
        return 'use_existing_repository'
    elif user_input == '2':
        return 'download_from_source'
    else:
        return user_input


def _create_new_repository() -> None:
    print('New repository setup')
    print('--------------------')

    home = Path(os.environ.get('HOME'))
    cwd = Path(os.getcwd())

    repo_name = input('Repository name: [.dotfiles] ')

    if repo_name == '':
        repo_name = '.dotfiles'

    if home != cwd:
        print(f'Location of {repo_name}:')
        print(f'[0] Home: {home}/{repo_name}')
        print(f'[1] Cwd: {cwd}/{repo_name}')
        user_input = input(' > ')

        if user_input == '0':
            repo_path = home / repo_name
        elif user_input == '1':
            repo_path = cwd / repo_name
        else:
            print('Exiting...')
            sys.exit()
    else:
        repo_path = cwd / repo_name

    work_tree = input(f'Default work tree: [{home}] ')

    if work_tree is None:
        work_tree_path = home
    else:
        work_tree_path = cwd / work_tree

    if repo_path.exists():
        print(f'{repo_path} already exists.')
        print('Exiting...')
        sys.exit()

    git_path = repo_path / '.git'

    _generateconfig_file(git_path, work_tree_path)

    try:
        repo_path.mkdir()
        os.chdir(repo_path)
        os.system('git init')
        print(f'Dotfile repository created at {repo_path}')
    except Exception as e:
        print(e)
        print('An error occured creating the repository.')
        print('Please report an issue at https://github.com/kylepollina/dot')
        print('Exiting...')
        sys.exit()


def _use_existing_repository() -> None:
    print('Existing repository setup')
    print('-------------------------')

    home = Path(os.environ.get('HOME'))
    cwd = Path(os.getcwd())

    repo_name = input('Repository name: ')
    repo_path = cwd / repo_name

    if repo_path.exists() is False:
        print(f'Could not locate directory {repo_path}')
        print('Exiting...')
        sys.exit()

    git_path = repo_path / '.git'
    if git_path.exists() is False:
        print(f'Could not locate git repository {git_path}')
        print('Exiting...')
        sys.exit()

    work_tree_path = input(f'Work tree directory: [{home}] ')
    if work_tree_path == '':
        work_tree_path = home

    _generateconfig_file(git_path, work_tree_path)
    print(f'Dotfiles setup at {repo_path}')

    """
        Look in newly setup repository for non git files.
        Ask to move them into the working tree
    """
    print()
    files = [filename for filename in os.listdir(_repo_path()) if os.path.isfile(_repo_path() / filename)]
    directories = [dirname for dirname in os.listdir(_repo_path()) if os.path.isdir(_repo_path() / dirname)]
    directories.remove('.git')

    if len(files) == 0 and len(directories) == 0:
        return

    print('Analyzing dotfile repository...')
    print(f'There is {len(files)} files and {len(directories)} directories in {_repo_path()}')
    print()

    if len(files) > 0:
        print('Files')
        print('-----')
        for filename in files[:5]:
            print(filename)
        if len(files) > 5:
            print('...')
        print()
    if len(directories) > 0:
        print('Directories')
        print('-----------')
        for directory in directories[:5]:
            print(directory)
        if len(directories) > 5:
            print('...')
        print()

    user_input = input('Would you like to move these into your work tree? (y/n [y]) ')

    if user_input.lower() == 'n' or user_input.lower() == 'no':
        return

    print()

    repo_path = _repo_path()

    for filename in files:
        file_path = repo_path / filename
        print(f'Moving file {file_path} to {work_tree()}')
        os.system(f'mv -iv {file_path} {work_tree()}')
        print()

    for directory in directories:
        processing_dir = work_tree() / directory
        print(f'Moving directory {directory} to {processing_dir}')
        if processing_dir.exists():
            print(f'Directory {processing_dir} already exists!')
            print('Considering moving this directory manually, as to not overwrite any current files.')
            continue
        else:
            os.system(f'mv -iv {directory} {work_tree()}')


def _generateconfig_file(git_dir, work_tree_path):
    print()
    print(f'Generated configs: {config_file()}')
    print()
    print('[dot]')
    print(f'git-dir={git_dir}')
    print(f'work-tree={work_tree_path}')
    print()

    user_input = input('Do you wish to continue? (y/n [y]) ')

    if user_input.lower() == 'n' or user_input.lower() == 'no':
        print('Exiting...')
        sys.exit()

    print()

    try:
        dot_home = _dot_home()
        if dot_home.exists() is False:
            dot_home.mkdir(parents=True)

        with open(config_file(), 'w+') as cfg:
            cfg.write('[dot]\n')
            cfg.write(f"git-dir='{git_dir}'\n")
            cfg.write(f"work-tree='{work_tree_path}'\n")

        print(f'Created config file at {config_file()}')

    except Exception as e:
        print(e)
        print('An error occured creating the config file.')
        print('Please report an issue at https://github.com/kylepollina/dot')
        print('Exiting...')
        sys.exit()
