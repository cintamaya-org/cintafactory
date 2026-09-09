module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = var.cluster_name
  cluster_version = "1.30"

  cluster_endpoint_public_access = true

  vpc_id                   = module.vpc.vpc_id
  subnet_ids               = module.vpc.private_subnets
  control_plane_subnet_ids = module.vpc.public_subnets

  enable_cluster_creator_admin_permissions = true

  # Optimisation des coûts (FinOps) & contournement des doublons d'alias/logs
  create_kms_key              = false
  create_cloudwatch_log_group = false
  cluster_encryption_config   = {}

  eks_managed_node_groups = {
    spot_nodes = {
      min_size     = 1
      max_size     = 3
      desired_size = 2

      # Multi-types d'instances pour garantir l'allocation Spot (contourne UnfulfillableCapacity)
      instance_types = ["t3.medium", "t3a.medium", "t2.medium"]
      capacity_type  = "SPOT"

      ami_type = "AL2023_x86_64_STANDARD"

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