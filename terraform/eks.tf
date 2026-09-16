
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

  # Optimisation des coûts (FinOps)
  create_kms_key              = false
  create_cloudwatch_log_group = false
  cluster_encryption_config   = {}

  eks_managed_node_groups = {
    spot_nodes = {
      min_size     = 1
      max_size     = 4
      desired_size = 2

      # Quota Spot vérifié le 16/09/2026 : 32 vCPU dispos sur la famille
      # Standard (A,C,D,H,I,M,R,T,Z) en eu-west-3, 0 utilisés.
      # m5.large = 2 vCPU / 8 Go RAM -> largement dans le quota.
      # t3.medium gardé en repli si m5.large manque de capacité Spot ponctuellement.
      instance_types = ["m5.large", "m5a.large", "t3.medium"]
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
