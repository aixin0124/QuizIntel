export function canManageTenant(role: string) {
  return ["owner", "tenant_owner", "survey_admin", "admin"].includes(role);
}

export function roleLabel(role: string) {
  const labels: Record<string, string> = {
    platform_admin: "平台管理员",
    owner: "个人账号所有者",
    tenant_owner: "个人账号所有者",
    survey_admin: "个人账号所有者",
    admin: "个人账号所有者",
    viewer: "兼容只读账号",
    member: "组内成员",
  };
  return labels[role] || role;
}
