// Output languages offered besides English (must match src/translator.py LANGUAGES).
export const LANGUAGES = { hi: "Hindi", bn: "Bengali", mr: "Marathi", ta: "Tamil", te: "Telugu", gu: "Gujarati", kn: "Kannada", ml: "Malayalam", pa: "Punjabi", or: "Odia" };
export const evaluationTone = { fail: "red", needs_review: "amber", pass_automated: "green", error: "red" };
export const evaluationLabel = { fail: "Fail", needs_review: "Needs review", pass_automated: "No rule fired", error: "Error" };
export const severityTone = { critical: "red", high: "red", review: "amber", info: "blue" };
export const percent = (value) => value == null ? "—" : `${Math.round(value * 100)}%`;
export const statusTone = (status) => status === "approved" ? "green" : status === "rejected" ? "red" : "amber";
export const statusLabel = (status) => status ? status.charAt(0).toUpperCase() + status.slice(1).replace("_", " ") : "None";
