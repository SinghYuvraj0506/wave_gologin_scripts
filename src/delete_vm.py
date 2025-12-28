import requests
import subprocess

def delete_self_vm():
    def meta(path):
        return requests.get(
            f"http://metadata.google.internal/computeMetadata/v1/{path}",
            headers={"Metadata-Flavor": "Google"},
            timeout=2
        ).text

    project = meta("project/project-id")
    zone = meta("instance/zone").split("/")[-1]
    instance = meta("instance/name")

    subprocess.run([
        "gcloud", "compute", "instances", "delete", instance,
        "--zone", zone,
        "--project", project,
        "--quiet"
    ])

if __name__ == "__main__":
    try:
        print("Deleting VM...")
        delete_self_vm()
    except Exception as e:
        print(f"Error deleting VM: {str(e)}")

