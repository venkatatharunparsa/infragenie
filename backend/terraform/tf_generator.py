"""
Terraform Generator
Creates and manages Terraform workspace directories and HCL files on disk.
"""

import os
import shutil

class TerraformGenerator:
    def __init__(self, workspace_dir: str):
        """Set the terraform_workspace directory path."""
        self.workspace_dir = workspace_dir
        os.makedirs(self.workspace_dir, exist_ok=True)

    def get_workspace_path(self, request_id: str) -> str:
        """Returns full path to workspace."""
        return os.path.join(self.workspace_dir, request_id)

    def create_workspace(self, request_id: str) -> str:
        """Creates a new subdirectory in workspace_dir named by request_id."""
        path = self.get_workspace_path(request_id)
        os.makedirs(path, exist_ok=True)
        return path

    def write_tf_files(self, request_id: str, tf_code: str) -> list[str]:
        """Splits the HCL into logical files (main.tf, variables.tf, outputs.tf) and writes them."""
        path = self.get_workspace_path(request_id)
        os.makedirs(path, exist_ok=True)
        
        lines = tf_code.split('\n')
        
        variables_hcl = []
        outputs_hcl = []
        main_hcl = []
        
        current_dest = main_hcl
        brace_count = 0
        
        for line in lines:
            stripped = line.strip()
            
            # Switch destination if we are outside of any block
            if brace_count == 0:
                if stripped.startswith('variable '):
                    current_dest = variables_hcl
                elif stripped.startswith('output '):
                    current_dest = outputs_hcl
                else:
                    current_dest = main_hcl
                    
            current_dest.append(line)
            
            brace_count += line.count('{') - line.count('}')
            
            # Add a blank line to separate blocks visually if returning to root level
            if brace_count == 0 and len(stripped) > 0:
                if current_dest is not main_hcl:
                    current_dest.append('')
        
        created_files = []
        
        if any(line.strip() for line in main_hcl):
            main_path = os.path.join(path, "main.tf")
            with open(main_path, "w", encoding="utf-8") as f:
                f.write('\n'.join(main_hcl).strip() + '\n')
            created_files.append(main_path)
            
        if any(line.strip() for line in variables_hcl):
            var_path = os.path.join(path, "variables.tf")
            with open(var_path, "w", encoding="utf-8") as f:
                f.write('\n'.join(variables_hcl).strip() + '\n')
            created_files.append(var_path)
            
        if any(line.strip() for line in outputs_hcl):
            out_path = os.path.join(path, "outputs.tf")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write('\n'.join(outputs_hcl).strip() + '\n')
            created_files.append(out_path)
            
        return created_files

    def write_backend_config(self, request_id: str, s3_bucket: str, dynamodb_table: str, region: str):
        """Writes backend.tf with S3 remote state config and DynamoDB lock config."""
        path = self.get_workspace_path(request_id)
        os.makedirs(path, exist_ok=True)
        backend_hcl = f"""terraform {{
  backend "s3" {{
    bucket         = "{s3_bucket}"
    key            = "infragenie/requests/{request_id}/terraform.tfstate"
    region         = "{region}"
    dynamodb_table = "{dynamodb_table}"
    encrypt        = true
  }}
}}
"""
        with open(os.path.join(path, "backend.tf"), "w", encoding="utf-8") as f:
            f.write(backend_hcl)

    def write_provider_config(self, request_id: str, region: str):
        """Writes provider.tf with AWS provider block."""
        path = self.get_workspace_path(request_id)
        os.makedirs(path, exist_ok=True)
        provider_hcl = f"""provider "aws" {{
  region = "{region}"
}}
"""
        with open(os.path.join(path, "provider.tf"), "w", encoding="utf-8") as f:
            f.write(provider_hcl)

    def cleanup_workspace(self, request_id: str):
        """Deletes the workspace directory after use."""
        path = self.get_workspace_path(request_id)
        if os.path.exists(path):
            shutil.rmtree(path)
