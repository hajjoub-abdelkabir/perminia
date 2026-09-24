import React from 'react';
import DailyPlan from './DailyPlan';
import {SchoolTasks} from './SchoolPortal';
export default function StudentToday({user,onLogin,onNavigate,onSeries}){
 if(!user)return <section className="sd-welcome"><h1>خطوتك اليوم، كتقرّبك للرخصة.</h1><p>دخل للحساب باش تلقى مهام الأستاذ وبرنامج القراءة ديالك.</p><button className="primary" onClick={onLogin}>تسجيل الدخول</button><button className="secondary" onClick={()=>onNavigate('lessons')}>استكشاف الدروس</button></section>;
 return <div className="student-today"><span className="eyebrow">اليوم · خطوة بخطوة</span><h1>مرحبا {user.display_name.split(' — ')[0]} 👋</h1><p>بدا بمهمة الأستاذ، أو كمل قراءة اليوم. التقدم ديالك كيتحفظ باش ترجع منين وقفتي.</p><SchoolTasks onLesson={slug=>onNavigate('lessons',slug)} onSeries={onSeries}/><DailyPlan onNavigate={onNavigate}/></div>;
}
