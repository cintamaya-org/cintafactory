module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = "1.30"

  # Accès API Server sécurisé
  cluster_endpoint_public_access = true

  vpc_id                   = module.vpc.vpc_id
  subnet_ids               = module.vpc.private_subnets
  control_plane_subnet_ids = module.vpc.public_subnets

  # Active l'authentification native EKS Access Entries (remplace aws-auth ConfigMap)
  enable_cluster_creator_admin_permissions = true

  # Node Group éphémère optimisé pour le coût
  eks_managed_node_groups = {
    spot_nodes = {
      min_size     = 1
      max_size     = 3
      desired_size = 2

      instance_types = ["t3.medium"]
      capacity_type  = "SPOT"

      labels = {
        Environment = var.environment
        Workload    = "load-test"
      }

      tags = {
        Environment = var.environment
        ManagedBy   = "Terraform"
      }
    }
  }

  tags = {
    Environment = var.environment
    ManagedBy   = "Terraform"
  }
}