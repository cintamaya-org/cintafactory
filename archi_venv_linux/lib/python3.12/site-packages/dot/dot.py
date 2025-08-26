import os
import sys

import click
import toml
from dot import config as cfg

CONTEXT_SETTINGS = {
    'ignore_unknown_options': True,
    'help_option_names': ['-h', '--help']
}


@click.group(context_settings=CONTEXT_SETTINGS)
def cli():
    """
    ┌───────────────────────────────────────────────────────┐                       
    │ `dot` is an elegant git wrapper for managing dotfiles │
    └───────────────────────────────────────────────────────┘
    https://github.com/kylepollina/dot

    All valid git commands/arguments work with dot. Just call `dot` with the git arguments you would like to use.

    Ex:
      dot log
      dot status
      etc.
    """


def main():
    """Main CLI entrypoint"""
    dot_arguments = ['s', 'au', 'cwf', 'list', 'init', 'config', '-h', '--help']
    if len(sys.argv) == 1 or sys.argv[1] in dot_arguments:
        cli()
    else:
        run_as_git_command()


def run_as_git_command():
    full_command = f'{cfg.git_command()} {original_args()}'
    os.system(full_command)


def original_args() -> str:
    """
    Returns the original arguments passed to dot
    Adds quotes around arguments containing spaces since the shell removes
     before passing to python
    """
    return " ".join(
        [f'\'{arg}\'' if len(arg.split()) > 1 else arg for arg in sys.argv[1:]]
    )


@cli.command()
def s():
    """
    Print the status of currently tracked files.
    Equivalent to

        git status -uno
    """
    full_command = f'{cfg.git_command()} status -uno'
    os.system(full_command)


@cli.command()
def au():
    """
    Add currently tracked files to index.
    Equivalent to

        git add -u
    """
    full_command = f'{cfg.git_command()} add -u'
    os.system(full_command)


@cli.command()
@click.option('-m')
def cwf(m):
    """Commit with filenames sorted by how they were changed."""
    added_files = cfg.diff_filter('A')
    copied_files = cfg.diff_filter('C')
    deleted_files = cfg.diff_filter('D')
    modified_files = cfg.diff_filter('M')
    renamed_files = cfg.diff_filter('R')

    commit_message = ''

    if m:
        commit_message += f'{m}\n'

    if len(added_files) > 0:
        commit_message += f'Added: {[f for f in added_files]}\n'
    if len(copied_files) > 0:
        commit_message += f'Copied: {[f for f in copied_files]}\n'
    if len(deleted_files) > 0:
        commit_message += f'Deleted: {[f for f in deleted_files]}\n'
    if len(modified_files) > 0:
        commit_message += f'Modified: {[f for f in modified_files]}\n'
    if len(renamed_files) > 0:
        commit_message += f'Renamed: {[f for f in renamed_files]}\n'

    full_command = f'{cfg.git_command()} commit -m "{commit_message}"'
    os.system(full_command)


@cli.command()
def list():
    """
    List the currently tracked files.
    Equivalent to

        git ls-tree --full-tree -r --name-only HEAD
    """
    full_command = f'{cfg.git_command()} ls-tree --full-tree -r --name-only HEAD'
    os.system(full_command)


@cli.command()
def init():
    """Initialize dotfile repository."""
    cfg.init()


@cli.group(invoke_without_command=True)
def config():
    """Config file information."""
    print(cfg.config_file())
    print(''.join('-' for c in str(cfg.config_file())))
    print(toml.dumps(toml.load(cfg.config_file())))
    print('Set the $DOT_HOME environment variable to point to the directory where you want to keep your config file')


@config.command()
def edit():
    """Open the configuration file for editing"""
    if cfg.config_file().exists():
        os.system(f'$EDITOR {cfg.config_file()}')
    else:
        print(f'Error! Trying to open config file {cfg.config_file()} but file does not exist.')
