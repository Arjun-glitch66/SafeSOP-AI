import { useState } from "react";
import { KeyRound, UserPlus, Users } from "lucide-react";
import { createUser, getUsers, updateUser } from "../api.js";
import { EmptyState } from "../components/ui.jsx";
import { useAuth, useNotice, useResource, useTitle } from "../state.jsx";

const ROLES = [
  ["author", "Author: uploads SOPs, requests changes, generates drafts"],
  ["reviewer", "Reviewer: records review decisions and finding verdicts"],
  ["admin", "Admin: everything, plus users and the audit log"],
];
const MIN_PASSWORD = 10;  // app/config.py MIN_PASSWORD_LENGTH; the server checks it again

// Admin only (the route and every API call check it). Every change is written to the audit log.
export default function UsersPage() {
  useTitle("Users");
  const { user: me } = useAuth();
  const { show } = useNotice();
  const users = useResource(getUsers, []);
  const [form, setForm] = useState({ username: "", password: "", role: "author" });
  const [busy, setBusy] = useState(false);
  const [resetFor, setResetFor] = useState(null);
  const [resetPassword, setResetPassword] = useState("");

  async function add(event) {
    event.preventDefault();
    if (form.password.length < MIN_PASSWORD) { show(`The password needs at least ${MIN_PASSWORD} characters.`, "error"); return; }
    setBusy(true);
    try {
      await createUser(form.username.trim(), form.password, form.role);
      show(`User ${form.username.trim()} created.`);
      setForm({ username: "", password: "", role: "author" });
      users.reload();
    } catch (error) {
      show(`Could not create the user: ${error.message}`, "error");
    } finally {
      setBusy(false);
    }
  }

  async function changeRole(target, role) {
    try {
      await updateUser(target.id, { role });
      show(`${target.username} is now ${role}.`);
    } catch (error) {
      show(`Could not change the role: ${error.message}`, "error");
    }
    users.reload();
  }

  async function reset(event) {
    event.preventDefault();
    if (resetPassword.length < MIN_PASSWORD) { show(`The password needs at least ${MIN_PASSWORD} characters.`, "error"); return; }
    try {
      await updateUser(resetFor.id, { password: resetPassword });
      show(`Password for ${resetFor.username} reset. Their open sessions have ended; give them the new password securely.`);
      setResetFor(null);
      setResetPassword("");
    } catch (error) {
      show(`Could not reset the password: ${error.message}`, "error");
    }
  }

  return (
    <>
      <div className="page-intro"><div><h1>Users</h1><p>Create accounts, change roles and reset passwords. Every change is recorded in the audit log. Whoever generates a draft can never approve it.</p></div></div>

      <section className="panel" aria-labelledby="new-user-heading">
        <div className="panel-heading"><div><h2 id="new-user-heading">New user</h2></div></div>
        <form onSubmit={add}>
          <label className="field-label" htmlFor="new-username">Username</label>
          <input id="new-username" className="form-input" autoComplete="off" required maxLength={100} value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} />
          <label className="field-label" htmlFor="new-password">Initial password (at least {MIN_PASSWORD} characters)</label>
          <input id="new-password" className="form-input" type="password" autoComplete="new-password" required value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} />
          <label className="field-label" htmlFor="new-role">Role</label>
          <select id="new-role" className="form-input" value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>
            {ROLES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
          <div className="action-row"><button className="btn btn-primary" disabled={busy}><UserPlus size={16} /> {busy ? "Creating…" : "Create user"}</button></div>
        </form>
      </section>

      <section className="panel" aria-labelledby="users-heading">
        <div className="panel-heading"><div><h2 id="users-heading">Accounts</h2><p>Role changes take effect on the user's next request.</p></div></div>
        {users.error && <p className="form-error" role="alert">Could not load users: {users.error.message}</p>}
        {users.data?.length === 0 && <EmptyState icon={Users} title="No users" text="Create the first account above." />}
        {users.data?.length > 0 && <div className="table-wrap"><table className="data-table">
          <thead><tr><th>Username</th><th>Role</th><th>Created</th><th><span className="sr-only">Password</span></th></tr></thead>
          <tbody>{users.data.map((item) => (
            <tr key={item.id}>
              <td><strong>{item.username}</strong>{item.id === me.id ? " (you)" : ""}</td>
              <td>
                <label className="sr-only" htmlFor={`role-${item.id}`}>Role of {item.username}</label>
                <select id={`role-${item.id}`} className="form-input" value={item.role} onChange={(event) => changeRole(item, event.target.value)}>
                  {ROLES.map(([value]) => <option key={value} value={value}>{value}</option>)}
                </select>
              </td>
              <td>{new Date(item.created_at).toLocaleDateString()}</td>
              <td><button className="btn btn-secondary" onClick={() => { setResetFor(item); setResetPassword(""); }}><KeyRound size={15} /> Reset password</button></td>
            </tr>
          ))}</tbody>
        </table></div>}

        {resetFor && <form className="request-summary" onSubmit={reset}>
          <label className="field-label" htmlFor="reset-password">New password for {resetFor.username}</label>
          <input id="reset-password" className="form-input" type="password" autoComplete="new-password" required value={resetPassword} onChange={(event) => setResetPassword(event.target.value)} />
          <div className="action-row">
            <button className="btn btn-primary">Set password</button>
            <button type="button" className="btn btn-secondary" onClick={() => setResetFor(null)}>Cancel</button>
          </div>
        </form>}
      </section>
    </>
  );
}
