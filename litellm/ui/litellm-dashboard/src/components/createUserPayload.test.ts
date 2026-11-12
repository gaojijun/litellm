import { describe, expect, it } from "vitest";
import { buildCreatePayload, parseOptionalRateLimit, withoutCollapsedModels } from "./createUserPayload";

const baseValues = {
  supply_user_id: false,
  user_email: "user@example.com",
  user_role: "internal_user",
  send_invite_email: true,
  tpm_limit: "",
  rpm_limit: "",
};

describe("parseOptionalRateLimit", () => {
  it("treats blank values as unlimited", () => {
    expect(parseOptionalRateLimit("")).toEqual({ ok: true, value: undefined });
    expect(parseOptionalRateLimit("   ")).toEqual({ ok: true, value: undefined });
    expect(parseOptionalRateLimit(null)).toEqual({ ok: true, value: undefined });
    expect(parseOptionalRateLimit(undefined)).toEqual({ ok: true, value: undefined });
  });

  it("accepts non-negative whole numbers", () => {
    expect(parseOptionalRateLimit(0)).toEqual({ ok: true, value: 0 });
    expect(parseOptionalRateLimit("100")).toEqual({ ok: true, value: 100 });
    expect(parseOptionalRateLimit(2500)).toEqual({ ok: true, value: 2500 });
  });

  it("rejects fractional, negative, and non-numeric values", () => {
    expect(parseOptionalRateLimit("-1")).toEqual({ ok: false });
    expect(parseOptionalRateLimit("1.5")).toEqual({ ok: false });
    expect(parseOptionalRateLimit("abc")).toEqual({ ok: false });
  });
});

describe("buildCreatePayload", () => {
  it("omits rate limits when they are blank", () => {
    const result = buildCreatePayload(baseValues);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.payload).not.toHaveProperty("tpm_limit");
    expect(result.payload).not.toHaveProperty("rpm_limit");
    expect(result.payload).toMatchObject({
      user_email: "user@example.com",
      user_role: "internal_user",
      models: ["no-default-models"],
    });
  });

  it("includes numeric TPM and RPM when set", () => {
    const result = buildCreatePayload({
      ...baseValues,
      tpm_limit: "100000",
      rpm_limit: "50",
    });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.payload).toMatchObject({
      tpm_limit: 100000,
      rpm_limit: 50,
    });
  });

  it("allows setting a zero rate limit", () => {
    const result = buildCreatePayload({
      ...baseValues,
      tpm_limit: "0",
      rpm_limit: "",
    });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.payload).toMatchObject({ tpm_limit: 0 });
    expect(result.payload).not.toHaveProperty("rpm_limit");
  });

  it("fails when a rate limit is invalid", () => {
    expect(buildCreatePayload({ ...baseValues, tpm_limit: "-5" }).ok).toBe(false);
    expect(buildCreatePayload({ ...baseValues, rpm_limit: "1.2" }).ok).toBe(false);
  });

  it("renames organization_ids to organizations", () => {
    const result = buildCreatePayload({
      ...baseValues,
      organization_ids: ["org-1"],
      tpm_limit: "10",
    });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.payload).not.toHaveProperty("organization_ids");
    expect(result.payload).toMatchObject({
      organizations: ["org-1"],
      tpm_limit: 10,
    });
  });
});

describe("withoutCollapsedModels", () => {
  it("drops models and access groups when the personal key section is collapsed", () => {
    const collapsed = withoutCollapsedModels({ ...baseValues, models: ["gpt-4"], access_group_ids: ["ag-1"] }, false);
    expect(collapsed).not.toHaveProperty("models");
    expect(collapsed).not.toHaveProperty("access_group_ids");
  });

  it("keeps models and access groups when the personal key section is open", () => {
    const open = withoutCollapsedModels({ ...baseValues, models: ["gpt-4"], access_group_ids: ["ag-1"] }, true);
    expect(open.models).toEqual(["gpt-4"]);
    expect(open.access_group_ids).toEqual(["ag-1"]);
  });
});
