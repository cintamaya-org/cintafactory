variable "aws_region" {
  description = "Région AWS pour le déploiement"
  type        = string
  default     = "eu-west-3"
}

variable "cluster_name" {
  description = "Nom du cluster EKS éphémère"
  type        = string
  default     = "cintafactory-poc"
}

variable "environment" {
  description = "Environnement cible"
  type        = string
  default     = "poc"
}