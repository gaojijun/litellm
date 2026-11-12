export type CreateUserFormValues = {
  supply_user_id: boolean;
  user_id?: string;
  user_email?: string;
  user_role: string;
  team_id?: string | null;
  organization_ids?: string[];
  metadata?: string;
  send_invite_email: boolean;
  models?: string[];
  access_group_ids?: string[];
  tpm_limit?: string | number | null;
  rpm_limit?: string | number | null;
};

const isBlank = (value: string | number | null | undefined): boolean =>
  value === null || value === undefined || String(value).trim() === "";

export type ParsedRateLimit = { ok: true; value: number | undefined } | { ok: false };

export const parseOptionalRateLimit = (value: string | number | null | undefined): ParsedRateLimit => {
  if (isBlank(value)) {
    return { ok: true, value: undefined };
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || !Number.isInteger(parsed) || parsed < 0) {
    return { ok: false };
  }
  return { ok: true, value: parsed };
};

// antd reported only mounted fields, so a collapsed Personal Key Creation
// section left `models` out of the request entirely even after the admin had
// picked some and closed it again. Access groups live in that same section.
export const withoutCollapsedModels = (
  values: CreateUserFormValues,
  isPersonalKeyOpen: boolean,
): CreateUserFormValues => {
  if (isPersonalKeyOpen) {
    return values;
  }
  const { models, access_group_ids, ...rest } = values;
  return rest;
};

export const buildCreatePayload = (values: CreateUserFormValues) => {
  const { supply_user_id, user_id, tpm_limit, rpm_limit, ...fields } = values;
  const apiValues = supply_user_id ? { ...fields, user_id: user_id?.trim() } : fields;
  const withModels =
    (!values.models || values.models.length === 0) && values.user_role !== "proxy_admin"
      ? { ...apiValues, models: ["no-default-models"] }
      : apiValues;

  const tpmLimit = parseOptionalRateLimit(tpm_limit);
  const rpmLimit = parseOptionalRateLimit(rpm_limit);
  if (!tpmLimit.ok || !rpmLimit.ok) {
    return { ok: false as const };
  }

  const withRateLimits = {
    ...withModels,
    ...(tpmLimit.value !== undefined && { tpm_limit: tpmLimit.value }),
    ...(rpmLimit.value !== undefined && { rpm_limit: rpmLimit.value }),
  };

  if (!withRateLimits.organization_ids) {
    return { ok: true as const, payload: withRateLimits };
  }
  const { organization_ids, ...rest } = withRateLimits;
  return { ok: true as const, payload: { ...rest, organizations: organization_ids } };
};
