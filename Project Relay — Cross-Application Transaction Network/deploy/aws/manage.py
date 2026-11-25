#!/usr/bin/env python3
"""Optional AWS stack commands. No AWS calls occur until an action is selected."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
TEMPLATE = HERE / "template.yaml"


def aws(args, *command, capture=False):
    options = ["aws", "--region", args.region]
    if args.profile:
        options += ["--profile", args.profile]
    result = subprocess.run([*options, *command], check=True, text=True,
                            capture_output=capture,
                            env={**os.environ, "AWS_PAGER": "", "AWS_CLI_AUTO_PROMPT": "off"})
    return result.stdout.strip() if capture else None


def revision(value):
    if value is None:
        value = subprocess.run(["git", "-C", str(PROJECT), "rev-parse", "HEAD"],
                               check=True, capture_output=True, text=True).stdout.strip()
    if not re.fullmatch(r"[a-fA-F0-9]{40}", value):
        raise ValueError("Supply a full 40-character commit SHA.")
    return value


def parameters(args):
    return json.dumps([{"ParameterKey": key, "ParameterValue": value}
                       for key, value in {
                           "VpcId": args.vpc_id,
                           "SubnetId": args.subnet_id,
                           "InstanceType": args.instance_type,
                           "VolumeSize": str(args.volume_size),
                           "ProjectRevision": revision(args.revision),
                       }.items()])


def instance_id(args):
    value = aws(args, "cloudformation", "describe-stacks", "--stack-name", args.stack,
                "--query", "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue | [0]",
                "--output", "text", capture=True)
    if not re.fullmatch(r"i-[a-f0-9]{8,17}", value):
        raise RuntimeError("The stack does not have an EC2 instance output yet.")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", required=True)
    parser.add_argument("--stack", default="project-relay")
    parser.add_argument("--profile", help="Optional existing AWS CLI profile")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("validate", help="Ask CloudFormation to validate the template")
    create = actions.add_parser("deploy", help="Create a new billable AWS stack")
    create.add_argument("--vpc-id", required=True)
    create.add_argument("--subnet-id", required=True)
    create.add_argument("--instance-type", default="t3.micro",
                        choices=["t3.micro", "t3.small", "t3a.micro", "t3a.small"])
    create.add_argument("--volume-size", type=int, choices=range(20, 101), default=20)
    create.add_argument("--revision", help="Public commit SHA; defaults to checked-out HEAD")
    actions.add_parser("status")
    actions.add_parser("shell")
    tunnel = actions.add_parser("tunnel")
    tunnel.add_argument("--local-port", type=int, default=8090)
    actions.add_parser("delete", help="Delete stack and its instance data; back up first")
    args = parser.parse_args(argv)

    if args.action == "validate":
        aws(args, "cloudformation", "validate-template",
            "--template-body", "file://" + str(TEMPLATE))
    elif args.action == "deploy":
        aws(args, "cloudformation", "create-stack", "--stack-name", args.stack,
            "--template-body", "file://" + str(TEMPLATE), "--capabilities", "CAPABILITY_IAM",
            "--parameters", parameters(args), "--tags", "Key=Project,Value=ProjectRelay")
        aws(args, "cloudformation", "wait", "stack-create-complete", "--stack-name", args.stack)
        print("Stack created. Cloud-init application bootstrap may still be running.")
    elif args.action == "status":
        aws(args, "cloudformation", "describe-stacks", "--stack-name", args.stack,
            "--query", "Stacks[0].{Status:StackStatus,Outputs:Outputs}", "--output", "json")
    elif args.action == "shell":
        aws(args, "ssm", "start-session", "--target", instance_id(args))
    elif args.action == "tunnel":
        if not 1024 <= args.local_port <= 65535:
            parser.error("--local-port must be 1024-65535")
        aws(args, "ssm", "start-session", "--target", instance_id(args),
            "--document-name", "AWS-StartPortForwardingSession",
            "--parameters", json.dumps({"portNumber":["8090"], "localPortNumber":[str(args.local_port)]}))
    elif args.action == "delete":
        aws(args, "cloudformation", "delete-stack", "--stack-name", args.stack)
        aws(args, "cloudformation", "wait", "stack-delete-complete", "--stack-name", args.stack)


if __name__ == "__main__":
    main()
