import os
import shutil
import re
import subprocess
from pathlib import Path
from packaging.version import Version, InvalidVersion
import json

def increment_patch_version(version: str) -> str:
    ver = Version(version)
    new_version = f"{ver.major}.{ver.minor}.{ver.micro + 1}"
    print(f"Incremented version from {version} to {new_version}")
    return new_version

def replace_version_in_file(file_path: Path, old_version: str, new_version: str) -> None:
    print(f"Replacing version in {file_path}: {old_version} -> {new_version}")
    content = file_path.read_text(encoding='utf-8')
    new_content = re.sub(re.escape(old_version), new_version, content)
    file_path.write_text(new_content, encoding='utf-8')

def detect_latest_version(app_path: Path) -> str:
    versions = sorted([d for d in app_path.iterdir() if d.is_dir() and is_valid_version(d.name)], key=lambda s: Version(s.name))
    latest_version = versions[-1].name if versions else None
    print(f"Detected latest version for {app_path}: {latest_version}")
    return latest_version

def update_app_versions_json(app_versions_file: Path, old_version: str, new_version: str) -> bool:
    if not app_versions_file.exists():
        print(f"Skipping update for app_versions.json because it does not exist at {app_versions_file}")
        return False

    print(f"Updating {app_versions_file} from version {old_version} to {new_version}...")
    updated = False
    with app_versions_file.open('r+', encoding='utf-8') as f:
        data = json.load(f)
        if old_version in data:
            entry = data.pop(old_version)
            entry["version"] = new_version
            data[new_version] = entry
            updated = True
        else:
            print(f"Version {old_version} not found in app_versions.json. Adding new version entry.")
            data[new_version] = {"version": new_version}

        if updated:
            f.seek(0)
            json.dump(data, f, indent=4)
            f.truncate()
            print(f"Updated app_versions.json from {old_version} to {new_version}.")

    return updated

def update_catalog_json(catalog_file: Path, app_name: str, old_version: str, new_version: str, docker_image_tag: str = None) -> bool:
    print(f"Updating {catalog_file} for app {app_name} from version {old_version} to {new_version}...")
    updated = False
    with catalog_file.open('r+', encoding='utf-8') as f:
        catalog_data = json.load(f)
        
        if app_name in catalog_data:
            app_entry = catalog_data[app_name]
            if app_entry.get("version") == old_version:
                app_entry["version"] = new_version
                if docker_image_tag:
                    app_entry["docker_image_tag"] = docker_image_tag
                updated = True
            else:
                print(f"Version {old_version} not found in catalog.json for {app_name}.")
        else:
            print(f"App {app_name} not found in catalog.json. Adding entry.")
            catalog_data[app_name] = {"version": new_version}
            if docker_image_tag:
                catalog_data[app_name]["docker_image_tag"] = docker_image_tag
            updated = True

        if updated:
            f.seek(0)
            json.dump(catalog_data, f, indent=4)
            f.truncate()
            print(f"Updated catalog.json for app {app_name} from {old_version} to {new_version}.")

    return updated

def clone_and_upgrade_version(app_path: Path, app_versions_file: Path, catalog_file: Path, app_name: str, latest_version: str, docker_image_tag: str = None) -> bool:
    new_version = increment_patch_version(latest_version)
    current_version_path = app_path / latest_version
    new_version_path = app_path / new_version

    # Ensure that a new version directory is created
    if not new_version_path.exists():
        shutil.copytree(
            current_version_path, 
            new_version_path, 
            ignore=shutil.ignore_patterns('*.tgz', 'app-changelog.md')
        )
        print(f"Created new version directory: {new_version_path}")

        # Update the Chart.yaml file in the new directory with the new version
        chart_file_path = new_version_path / "Chart.yaml"
        if chart_file_path.exists():
            print(f"Updating Chart.yaml at {chart_file_path} from {latest_version} to {new_version}")
            replace_version_in_file(chart_file_path, latest_version, new_version)

            # Update app_versions.json and catalog.json
            app_versions_updated = update_app_versions_json(app_versions_file, latest_version, new_version)
            catalog_updated = update_catalog_json(catalog_file, app_name, latest_version, new_version, docker_image_tag)
            
            return app_versions_updated or catalog_updated
    else:
        print(f"Version directory {new_version_path} already exists. Skipping creation.")

    return False

def is_valid_version(version_str: str) -> bool:
    try:
        Version(version_str)
        return True
    except InvalidVersion:
        print(f"Invalid version detected: {version_str}")
        return False

def get_modified_files() -> list:
    result = subprocess.run(['git', 'diff', '--name-only', 'HEAD~1', 'HEAD'], stdout=subprocess.PIPE, text=True)
    files = result.stdout.strip().split('\n')
    print(f"Modified files: {files}")
    return files

def get_file_diff(file_path: str) -> str:
    """Get the diff for a specific file between the last two commits."""
    result = subprocess.run(['git', 'diff', 'HEAD~1', 'HEAD', '--', file_path], stdout=subprocess.PIPE, text=True)
    print(f"Generated diff for {file_path}")
    return result.stdout

def check_for_version_change(chart_file_path: Path) -> bool:
    diff = get_file_diff(str(chart_file_path))
    print(f"Diff for {chart_file_path}:\n{diff}")
    version_changed = False
    for line in diff.splitlines():
        if line.startswith('+') and 'version:' in line:
            print(f"Detected version change in {chart_file_path}: {line.strip()}")
            version_changed = True
    return version_changed

def process_repository(base_dir: Path) -> bool:
    modified_files = get_modified_files()
    changes_made = False
    highest_version = None
    app_name = None
    app_path = None
    catalog_file = base_dir / "catalog.json"  # Assume catalog.json is in the root of the repository
    
    # Determine the highest version number across all modified files
    for file_path in modified_files:
        path = Path(file_path)
        if path.suffix == '.yaml' and 'Chart.yaml' in path.name:
            current_app_path = path.parent.parent
            current_app_name = current_app_path.name  # The name of the app
            print(f"Detected app: {current_app_name} in {current_app_path}")
            if app_name is None:
                app_name = current_app_name
                app_path = current_app_path

            current_version = detect_latest_version(current_app_path)
            if highest_version is None or Version(current_version) > Version(highest_version):
                highest_version = current_version

    if app_name and highest_version:
        app_versions_file = app_path / "app_versions.json"
        docker_image_tag = None
        for file_path in modified_files:
            path = Path(file_path)
            if path.suffix == '.yaml' and 'Chart.yaml' in path.name:
                # Extract docker image tag if it exists
                with path.open('r', encoding='utf-8') as f:
                    content = f.read()
                    match = re.search(r'image:\s*([^\s]+:\S+)', content)
                    if match:
                        docker_image_tag = match.group(1)
                        print(f"Detected Docker image tag: {docker_image_tag}")
                break  # We only need to extract the docker tag once

        changes_made = clone_and_upgrade_version(app_path, app_versions_file, catalog_file, app_name, highest_version, docker_image_tag)

    return changes_made

def commit_changes() -> None:
    print("Committing changes to git...")
    subprocess.run(['git', 'add', '.'])
    subprocess.run(['git', 'commit', '-m', 'ci: bump helm chart versions and update app_versions.json and catalog.json'])
    subprocess.run(['git', 'push'])

if __name__ == "__main__":
    base_dir = Path('./')  # Adjust as necessary
    if process_repository(base_dir):
        commit_changes()
    else:
        print("No changes detected.")