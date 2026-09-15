eks_managed_node_groups = {
    spot_nodes = {
      min_size     = 1
      max_size     = 3
      desired_size = 1

      # Instances modernes compatibles Spot sans conflit d'offre gratuite
      instance_types = ["t3.medium", "t3a.medium"]
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