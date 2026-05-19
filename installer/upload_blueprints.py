import argparse
import configparser
import json
import os
from pathlib import Path
from typing import Dict, List

import boto3

'''
    USAGE  
    python upload_blueprints.py <env> --aws-profile <profile> --aws-region <region>
    python upload_blueprints.py <env> --aws-profile <profile> --aws-region <region> --blueprint <blueprint>
'''


def get_available_aws_profiles():
    profiles = []
    aws_credentials_path = os.path.expanduser("~/.aws/credentials")
    aws_config_path = os.path.expanduser("~/.aws/config")

    if os.path.exists(aws_credentials_path):
        config = configparser.ConfigParser()
        config.read(aws_credentials_path)
        profiles.extend(config.sections())

    if os.path.exists(aws_config_path):
        config = configparser.ConfigParser()
        config.read(aws_config_path)
        for section in config.sections():
            if section.startswith("profile "):
                profile_name = section.replace("profile ", "")
                if profile_name not in profiles:
                    profiles.append(profile_name)

    return profiles if profiles else ["default"]


def get_profile_region(profile_name: str) -> str:
    config = configparser.ConfigParser()
    config_path = os.path.expanduser("~/.aws/config")

    if os.path.exists(config_path):
        config.read(config_path)
        profile_section = f"profile {profile_name}" if profile_name != "default" else "default"
        if profile_section in config and "region" in config[profile_section]:
            return config[profile_section]["region"]

    return "us-east-1"


def load_blueprint_files(blueprint_name: str = None) -> List[Dict]:
    current_dir = Path(__file__).parent
    blueprints_dir = current_dir.parent / "blueprints"
    if not blueprints_dir.exists():
        raise FileNotFoundError("Blueprints directory not found")

    blueprints = []
    if blueprint_name:
        files = [blueprints_dir / f"{blueprint_name}.json"]
    else:
        files = list(blueprints_dir.glob("*.json"))

    for json_file in files:
        if not json_file.exists():
            raise FileNotFoundError(f"Blueprint file '{json_file.name}' not found")
        with open(json_file, "r", encoding="utf-8") as f:
            blueprint = json.load(f)
            if "irn" not in blueprint:
                blueprint["irn"] = f"irn:blueprint:irma:{json_file.stem}"
            blueprints.append(blueprint)

    return blueprints


def upload_blueprints(dynamodb, table_name: str, blueprints: List[Dict]) -> Dict[str, List[str]]:
    table = dynamodb.Table(table_name)
    results = {"success": [], "failed": []}

    for blueprint in blueprints:
        try:
            if "irn" not in blueprint:
                raise ValueError("Blueprint missing 'irn' field")
            if "version" not in blueprint:
                blueprint["version"] = "latest"

            table.put_item(Item=blueprint)
            results["success"].append(f"{blueprint['irn']}@{blueprint['version']}")
            print(f"Uploaded blueprint: {blueprint['irn']}@{blueprint['version']}")
        except Exception as exc:
            results["failed"].append(f"{blueprint.get('irn', 'unknown')}: {str(exc)}")
            print(f"Failed to upload blueprint {blueprint.get('irn', 'unknown')}: {str(exc)}")

    return results


def run(env_name: str, aws_profile: str, region: str = None, blueprint_name: str = None) -> Dict[str, List[str]]:
    if region is None:
        region = get_profile_region(aws_profile)

    boto3.setup_default_session(profile_name=aws_profile)
    dynamodb = boto3.resource("dynamodb", region_name=region)
    blueprints = load_blueprint_files(blueprint_name)
    table_name = f"{env_name}_blueprints"
    return upload_blueprints(dynamodb, table_name, blueprints)


def main():
    parser = argparse.ArgumentParser(description="Upload Gro blueprint JSON files to DynamoDB.")
    parser.add_argument("environment_name", type=str, help="Environment name (e.g., dev, prod, test)")

    available_profiles = get_available_aws_profiles()
    parser.add_argument(
        "--aws-profile",
        type=str,
        choices=available_profiles,
        default="default",
        help=f"Specify AWS profile ({', '.join(available_profiles)})",
    )
    parser.add_argument("--aws-region", type=str, help="AWS region")
    parser.add_argument("--blueprint", type=str, help="Single blueprint name without extension")
    args = parser.parse_args()

    results = run(args.environment_name, args.aws_profile, args.aws_region, args.blueprint)
    print(f"Successfully uploaded {len(results['success'])} blueprints")
    if results["failed"]:
        print(f"Failed uploads: {len(results['failed'])}")


if __name__ == "__main__":
    main()
