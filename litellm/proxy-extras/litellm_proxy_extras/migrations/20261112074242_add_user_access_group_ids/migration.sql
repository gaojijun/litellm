-- AlterTable
ALTER TABLE "LiteLLM_UserTable" ADD COLUMN IF NOT EXISTS "access_group_ids" TEXT[] DEFAULT ARRAY[]::TEXT[];

-- AlterTable
ALTER TABLE "LiteLLM_AccessGroupTable" ADD COLUMN IF NOT EXISTS "assigned_user_ids" TEXT[] DEFAULT ARRAY[]::TEXT[];
