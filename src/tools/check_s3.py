import boto3

# S3 Client erstellen
s3 = boto3.client("s3")

# Alle Buckets abrufen
response = s3.list_buckets()

print("\nAvailable S3 Buckets:\n")

# Bucketnamen ausgeben
for bucket in response["Buckets"]:
    print(f"- {bucket['Name']}")

print("\nS3 connection successful.")
