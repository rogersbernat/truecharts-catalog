import os
import shutil
import re
import subprocess
from pathlib import Path
from packaging.version import Version, InvalidVersion

def increment_patch_version(version: str) -> str:
    ver = Version(version)
    return f"{ver.major}.{ver.minor}.{ver.micro + 1}"

def replace_version_in_file(file_path: Path, old_version: str, new_version: str) -> None:
    content = file_path.read_text(encoding='utf-8')
    new_content = re.sub(re.escape(old_version), new_version, content)
    file_path.write_text(new_content, encoding='utf-8')

def clone_and_upgrade_version(app_path: Path, old_version: str) -> None:
    new_version = increment_patch_version(old_version)
    current_version_path = app_path / old_version
    new_version_path = app_path / new_version

    # Copy the entire directory tree from the old version to the new version
    shutil.copytree(current_version_path, new_version_path)
    print(f"Created new version directory: {new_version_path}")

    # Update the Chart.yaml file in the new version directory
    chart_file_path = new_version_path / "Chart.yaml"
    if chart_file_path.exists():
        replace_version_in_file(chart_file_path, old_version, new_version)
        print(f"Updated Chart.yaml version from {old_version} to {new_version}")

def is_valid_version(version_str: str) -> bool:
    try:
        Version(version_str)
        return True
    except InvalidVersion:
        return False

def get_modified_files() -> list:
    result = subprocess.run(['git', 'diff', '--name-only', 'HEAD~1', 'HEAD'], stdout=subprocess.PIPE, text=True)
    return result.stdout.strip().split('\n')

def process_repository(base_dir: Path) -> bool:
    modified_files = get_modified_files()
    changes_made = False
    
    for file_path in modified_files:
        path = Path(file_path)
        if path.suffix == '.yaml' and 'Chart.yaml' in path.name:
            app_path = path.parent.parent
            old_version = path.parent.name
            if app_path.is_relative_to(base_dir) and is_valid_version(old_version):
                clone_and_upgrade_version(app_path, old_version)
                changes_made = True
    
    return changes_made

def commit_changes() -> None:
    subprocess.run(['git', 'add', '.'])
    subprocess.run(['git', 'commit', '-m', 'ci: bump helm chart versions'])
    subprocess.run(['git', 'push'])

if __name__ == "__main__":
    base_dir = Path('./')  # Adjust as necessary
    if process_repository(base_dir):
        commit_changes()