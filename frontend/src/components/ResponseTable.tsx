import { Ban, CheckCircle2, FlaskConical, RotateCcw, Trash2 } from "lucide-react";
import { useState } from "react";
import { adminDeleteJson, adminPostJson } from "../api/client";
import type { ResponseRow } from "../types";
import { canManageTenant } from "../permissions";

type ResponseTableProps = {
  rows: ResponseRow[];
  token: string;
  role: string;
  onChanged: (rows: ResponseRow[]) => void;
};

export function ResponseTable({ rows, token, role, onChanged }: ResponseTableProps) {
  const canManage = canManageTenant(role);
  const [message, setMessage] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  async function markInvalid(row: ResponseRow, invalid: boolean) {
    if (!canManage) return;
    const reason = invalid ? window.prompt("请输入无效原因（可选）：", row.invalid_reason || "") || "" : "";
    setBusyId(row.id);
    setMessage("");
    try {
      await adminPostJson(`/api/responses/${row.id}/invalid`, { invalid, reason }, token);
      onChanged(rows.map((item) => item.id === row.id ? { ...item, is_invalid: invalid, invalid_reason: invalid ? reason : null } : item));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "答卷状态更新失败。");
    } finally {
      setBusyId(null);
    }
  }

  async function deleteRow(row: ResponseRow) {
    if (!canManage || !window.confirm(`确定删除答卷 #${row.id} 吗？`)) return;
    setBusyId(row.id);
    setMessage("");
    try {
      await adminDeleteJson(`/api/responses/${row.id}`, token);
      onChanged(rows.filter((item) => item.id !== row.id));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "答卷删除失败。");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="response-table panel">
      <div className="section-heading">
        <div>
          <h2><CheckCircle2 size={19} /> 答卷明细与有效性</h2>
          <p>正式统计只排除明确测试和无效答卷，后台浏览来源默认计入。</p>
        </div>
        <strong>{rows.length} 条记录</strong>
      </div>
      {message && <div className="form-error">{message}</div>}
      {!rows.length ? <div className="empty">暂时没有答卷记录。</div> : <div className="response-table-wrap"><table><thead><tr><th>编号</th><th>来源</th><th>结果</th><th>版本</th><th>提交时间</th><th>耗时</th><th>状态</th><th>操作</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>#{row.id}</td><td><span className="response-source">{sourceLabel(row.source)}{row.is_test && <FlaskConical size={13} />}</span></td><td>{row.result_type}</td><td>v{row.survey_version}</td><td>{formatDate(row.submitted_at || row.created_at)}</td><td>{row.duration_seconds ? `${row.duration_seconds}s` : "未记录"}</td><td>{row.is_invalid ? <span className="response-invalid">无效</span> : row.is_test ? <span className="response-test">测试</span> : <span className="response-valid">有效</span>}</td><td><div className="response-actions">{canManage && !row.is_invalid && <button className="icon-button subtle-danger" onClick={() => void markInvalid(row, true)} disabled={busyId === row.id} title="标记为无效" aria-label={`标记答卷${row.id}为无效`}><Ban size={15} /></button>}{canManage && row.is_invalid && <button className="icon-button" onClick={() => void markInvalid(row, false)} disabled={busyId === row.id} title="恢复有效" aria-label={`恢复答卷${row.id}`}><RotateCcw size={15} /></button>}{canManage && <button className="icon-button subtle-danger" onClick={() => void deleteRow(row)} disabled={busyId === row.id} title="删除答卷" aria-label={`删除答卷${row.id}`}><Trash2 size={15} /></button>}</div></td></tr>)}</tbody></table></div>}
      {!canManage && <p className="field-hint">当前账号为只读查看者，不能修改或删除答卷。</p>}
    </section>
  );
}

function sourceLabel(source: string) {
  return source === "public_link" ? "公开链接" : source === "admin_preview" ? "后台浏览" : source === "test" ? "测试答卷" : source;
}

function formatDate(value: string) {
  return value.replace("T", " ");
}
