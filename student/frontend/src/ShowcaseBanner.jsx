import React from 'react';

export default function ShowcaseBanner() {
  if (import.meta.env.VITE_SHOWCASE !== 'true') return null;
  return <aside className="showcase-banner" aria-label="حدود النسخة المعروضة" dir="rtl">
    <strong>PerminIA · عرض تقني للـMVP</strong>
    <span>الحسابات والتمارين اصطناعية باش تجرّب المسار؛ ماشي أسئلة بيرمي معتمدة. المساعد AI مطفّي فهاد النسخة.</span>
  </aside>;
}
