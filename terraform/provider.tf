terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  # La clé (key) est fournie à `terraform init -backend-config=key=...` par la CI,
  # pour isoler le state par environnement (dev/staging/production).
  backend "s3" {
    bucket         = "cintafactory-terraform-state"
    region         = "eu-west-3"
    dynamodb_table = "cintafactory-terraform-locks"
  }
}
