import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {BriefcaseBusiness, Upload, Users, ChevronRight, X, LoaderCircle, FileText, Pencil, Save, Eye} from 'lucide-react';
import './style.css';

const api = async (url, options={}) => {
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new Error('Cannot reach the API. Check that the backend is running at http://localhost:8000.');
  }
  const body = await response.text();
  let data = null;
  try { data = body ? JSON.parse(body) : null; } catch { /* Keep non-JSON server messages readable. */ }
  if (!response.ok) {
    throw new Error(data?.detail || body || `Request failed (${response.status})`);
  }
  if (body && data === null) throw new Error('The API returned an invalid response. Check the backend logs.');
  return data;
};
function projectParts(project){
  if(typeof project!=='string')return project;
  const [title,...details]=project.split('\n');
  return {title,details,tools:[],links:[]};
}
function scoreReason(component, score, candidate){
  const criteria=candidate.criteria||{};
  if(component==='skills'){
    const required=criteria.required_skills||[];
    if(score===null||!required.length)return 'No required skills were extracted from this role, so this component is not scored.';
    const matched=candidate.matched_skills||[],missing=candidate.missing_skills||[];
    return `Found ${matched.length} of ${required.length} required skills.${matched.length?` Matched: ${matched.join(', ')}.`:''}${missing.length?` Not found: ${missing.join(', ')}.`:''}`;
  }
  if(component==='semantic')return score===null?'Role or resume text was not available for semantic comparison.':'Compares the meaning of the job description with the resume text; related wording can match even without the exact same phrase.';
  if(component==='experience'){
    if(!criteria.min_experience)return 'The job description does not state a minimum experience requirement, so experience is not scored.';
    if(candidate.experience_years===null)return `The role asks for ${criteria.min_experience}+ years, but no reliable experience duration was identified in the resume.`;
    return `${candidate.experience_years} years identified against ${criteria.min_experience} required; the score scales proportionally and is capped at 100%.`;
  }
  if(component==='education'){
    const qualifications=criteria.qualifications||[];
    if(score===null||!qualifications.length)return 'No education requirement was extracted from the job description, so this component is not scored.';
    const records=candidate.education_records||[];
    const found=records.map(record=>[record.qualification,record.institution,record.result].filter(Boolean).join(' · ')).filter(Boolean);
    return `Role criteria: ${qualifications.join('; ')}. Resume evidence: ${found.slice(0,3).join(' | ')||'No grouped education evidence identified'}. Related technology branches may receive full field-match credit.`;
  }
  return '';
}
function App(){
  const [description,setDescription]=useState(''),[jdFile,setJdFile]=useState(null),[roleTitle,setRoleTitle]=useState(''),[roleMode,setRoleMode]=useState('new'),[editingRole,setEditingRole]=useState(false),[editTitle,setEditTitle]=useState(''),[editDescription,setEditDescription]=useState(''),[rolePreview,setRolePreview]=useState(null),[previewingRole,setPreviewingRole]=useState(false),[savingRole,setSavingRole]=useState(false),[reanalyzing,setReanalyzing]=useState(false),[search,setSearch]=useState(''),[job,setJob]=useState(null),[jobs,setJobs]=useState([]),[rows,setRows]=useState([]),[selected,setSelected]=useState(null),[showResume,setShowResume]=useState(false),[files,setFiles]=useState([]),[loading,setLoading]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  async function refreshJobs(){const data=await api('/api/jobs');setJobs(data);}
  async function selectJob(j){setJob(j);setSelected(null);setRows(await api(`/api/jobs/${j.id}/candidates`));}
  useEffect(()=>{refreshJobs().catch(e=>setError(e.message));},[]);
  useEffect(()=>{
    if(!job)return;
    let active=true;
    const refresh=async()=>{try{const latest=await api(`/api/jobs/${job.id}/candidates`);if(active)setRows(latest);}catch{}}
    const timer=setInterval(refresh,5000);
    return()=>{active=false;clearInterval(timer);};
  },[job?.id]);
  useEffect(()=>{
    if(!selected)return;
    const previous=document.body.style.overflow;
    const closeOnEscape=e=>{if(e.key==='Escape')setSelected(null);};
    document.body.style.overflow='hidden';window.addEventListener('keydown',closeOnEscape);
    return()=>{document.body.style.overflow=previous;window.removeEventListener('keydown',closeOnEscape);};
  },[selected]);
  async function matchCandidates(e){
    e.preventDefault();
    if(!files.length){setError('Choose at least one resume to continue.');return;}
    setLoading(true);setError('');setNotice('Preparing the role and matching resumes…');
    try{
      let activeJob=job;
      if(roleMode==='new'&&jdFile){const fd=new FormData();fd.append('file',jdFile);if(roleTitle.trim())fd.append('title',roleTitle.trim());activeJob=await api('/api/jobs/file',{method:'POST',body:fd});}
      else if(roleMode==='new'&&description.trim()){
        if(description.trim().length<20)throw new Error('The job description must be at least 20 characters.');
        activeJob=await api('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({description,title:roleTitle.trim()||undefined})});
      }
      if(!activeJob)throw new Error('Add a job description or choose a saved role.');
      setJob(activeJob);setRoleMode('saved');setJdFile(null);setDescription('');setRoleTitle('');await refreshJobs();
      const fd=new FormData();files.forEach(f=>fd.append('files',f));
      const result=await api(`/api/jobs/${activeJob.id}/resumes`,{method:'POST',body:fd});
      const failed=result.results.filter(x=>x.status==='error');
      setNotice(`${result.results.length-failed.length} resume(s) processed; ${failed.length} error(s), ${result.results.filter(x=>x.status==='duplicate').length} duplicate(s).`);
      await selectJob(activeJob);await refreshJobs();setFiles([]);
    }catch(e){setError(e.message);setNotice('');}finally{setLoading(false);}
  }
  async function inspect(c,viewResume=false){try{setSelected(await api(`/api/candidates/${c.id}`));setShowResume(viewResume);}catch(e){setError(e.message);}}
  function editSavedRole(){setEditTitle(job.title);setEditDescription(job.description);setRolePreview(null);setEditingRole(true);}
  async function previewRole(){
    if(!job)return;
    setPreviewingRole(true);setError('');
    try{const preview=await api(`/api/jobs/${job.id}/preview`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:editDescription})});setRolePreview({description:editDescription,...preview});}
    catch(e){setError(e.message);}finally{setPreviewingRole(false);}
  }
  async function saveRole(){
    if(!job||rolePreview?.description!==editDescription)return;
    setSavingRole(true);setError('');
    try{
      const updated=await api(`/api/jobs/${job.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:editTitle.trim(),description:editDescription})});
      setJob(updated);setJobs(current=>current.map(item=>item.id===updated.id?updated:item));setEditingRole(false);setRolePreview(null);await selectJob(updated);
    }catch(e){setError(e.message);}finally{setSavingRole(false);}
  }
  async function reanalyzeSavedCandidates(){
    if(!job||reanalyzing)return;
    setReanalyzing(true);setError('');
    try{const updated=await api(`/api/jobs/${job.id}/reanalyze`,{method:'POST'});setRows(updated);setNotice(`Reanalyzed ${updated.length} saved candidate(s) with the latest parsing and scoring rules.`);if(selected){const refreshed=updated.find(candidate=>candidate.id===selected.id);if(refreshed)setSelected(await api(`/api/candidates/${refreshed.id}`));}}
    catch(e){setError(e.message);}finally{setReanalyzing(false);}
  }
  const scoreColor=n=>n>=75?'good':n>=50?'mid':'low';
  const canSubmit=files.length>0&&(roleMode==='saved'?Boolean(job):Boolean(jdFile)||description.trim().length>=20);
  const visibleRows=rows.filter(candidate=>`${candidate.name||''} ${candidate.filename} ${candidate.matched_skills.join(' ')}`.toLowerCase().includes(search.toLowerCase()));
  const averageScore=rows.length?Math.round(rows.reduce((sum,c)=>sum+c.overall_score,0)/rows.length):0;
  const skillReasons=selected?[...selected.matched_skills.map(skill=>({skill,matched:true})),...selected.missing_skills.map(skill=>({skill,matched:false}))]:[];
  return <main className="shell"><header><div className="brand"><div className="logo"><BriefcaseBusiness size={20}/></div><div><strong>talent<span>lens</span></strong><small>AI resume matching</small></div></div><span className="top-label">RECRUITING WORKSPACE</span></header>
    <section className="intro"><div><div className="eyebrow">SMARTER SHORTLISTS</div><h1>Find the right people,<br/><em>with confidence.</em></h1><p>Match candidate experience to the work that matters.</p></div><div className="intro-mark"><Users size={36}/></div></section>
    {error&&<div className="alert">{error}<button onClick={()=>setError('')}><X size={15}/></button></div>}
    <form className="match-form" onSubmit={matchCandidates}>
      <section className="workspace">
        <aside className="left">
          <div className="section-head"><span className="step">01</span><div><h2>Choose a role</h2><p>Create a role or reuse one you saved</p></div></div>
          <div className="role-switch"><button type="button" className={roleMode==='new'?'active':''} onClick={()=>setRoleMode('new')}>New role</button><button type="button" className={roleMode==='saved'?'active':''} onClick={()=>{setRoleMode('saved');setDescription('');setJdFile(null);if(!job&&jobs.length)selectJob(jobs[0]);}}>Saved role</button></div>
          {roleMode==='new'?<div className="new-role-fields">
            <label className="field-label">Role name <span>Optional</span><input className="role-title-input" value={roleTitle} onChange={e=>setRoleTitle(e.target.value)} placeholder="Auto-detect from job description"/></label>
            <label className="jd-upload"><Upload size={14}/>{jdFile?'Replace job description':'Upload job description'}<input type="file" accept=".pdf,.docx" onChange={e=>{setJdFile(e.target.files[0]||null);setDescription('');}}/></label>
            {jdFile&&<div className="jd-attached"><FileText size={18}/><span><b>Job description attached</b><small>{jdFile.name}</small></span><button type="button" onClick={()=>setJdFile(null)}>Remove</button></div>}
            <textarea value={description} onChange={e=>{setDescription(e.target.value);setJdFile(null)}} placeholder={'Paste the job description here…\n\nInclude responsibilities, required skills, and qualifications.'}/>
          </div>:jobs.length?<label className="saved-role-label">Select a saved role<select value={job?.id||''} onChange={e=>{const found=jobs.find(item=>item.id===Number(e.target.value));if(found)selectJob(found);}}><option value="" disabled>Choose a role…</option>{jobs.map(j=><option key={j.id} value={j.id}>{j.title} · {j.candidate_count||0} candidates</option>)}</select></label>:<div className="empty role-empty">No saved roles yet.<span>Create a role first, then you can reuse it here.</span></div>}
        </aside>
        <section className="right">
          <div className="section-head"><span className="step">02</span><div><h2>Candidate resumes</h2><p>Upload one or more PDF / DOCX files</p></div></div>
          <label className="drop"><Upload size={24}/><b>Choose resume files</b><span>Up to 100 files · 15 MB max each</span><input type="file" multiple accept=".pdf,.docx" onChange={e=>setFiles([...e.target.files])}/></label>
          {files.length>0&&<div className="file-list">{files.map((f,i)=><span key={i}>{f.name}<button type="button" aria-label={`Remove ${f.name}`} onClick={()=>setFiles(files.filter((_,n)=>i!==n))}><X size={13}/></button></span>)}</div>}
          {roleMode==='saved'&&job&&<>
            <div className="role-chip"><div className="chip-icon"><BriefcaseBusiness size={16}/></div><div><b>Using saved role: {job.title}</b><small>{job.required_skills.length} required skills {job.min_experience?`· ${job.min_experience}+ years`:''}</small></div><button type="button" className="edit-role" onClick={editSavedRole}><Pencil size={14}/>Edit role</button></div>
            {editingRole&&<div className="role-editor">
              <label>Role name<input value={editTitle} onChange={e=>setEditTitle(e.target.value)} maxLength={200}/></label>
              <label>Job description<textarea value={editDescription} onChange={e=>{setEditDescription(e.target.value);setRolePreview(null);}} minLength={20} maxLength={50000}/></label>
              <div className="role-editor-actions"><button type="button" className="cancel-edit" onClick={()=>{setEditingRole(false);setRolePreview(null);}}>Cancel</button><button type="button" className="primary save-edit preview-edit" disabled={previewingRole||editDescription.trim().length<20} onClick={previewRole}>{previewingRole?<LoaderCircle className="spin" size={14}/>:null}Preview score changes</button><button type="button" className="primary save-edit" disabled={savingRole||!editTitle.trim()||editDescription.trim().length<20||rolePreview?.description!==editDescription} onClick={saveRole}>{savingRole?<LoaderCircle className="spin" size={14}/>:<Save size={14}/>}Save & apply</button></div>
              {rolePreview?.description===editDescription&&<div className="preview-panel"><div className="preview-heading"><b>Ranking impact preview</b><span>{rolePreview.candidate_count} candidate(s)</span></div>{rolePreview.candidates.length?<div className="preview-list">{rolePreview.candidates.slice(0,5).map(candidate=><div className="preview-row" key={candidate.id}><span>{candidate.name}</span><span>{candidate.previous_score}% <i>→</i> <b>{candidate.new_score}%</b></span><strong className={candidate.delta>0?'delta-up':candidate.delta<0?'delta-down':''}>{candidate.delta>0?'+':''}{candidate.delta}%</strong></div>)}</div>:<p>No candidates will be affected yet.</p>}</div>}
            </div>}
          </>}
          {notice&&<p className="notice">{notice}</p>}
        </section>
      </section>
      <button className="primary run-button" disabled={loading||!canSubmit}>{loading?<LoaderCircle className="spin" size={17}/>:null}{loading?'Analyzing and ranking…':'Analyze & rank candidates'}{!loading&&<ChevronRight size={17}/>}</button>
      <p className="form-caption">Your candidates are scored on skills, semantic fit, experience, and qualifications.</p>
    </form>
    {job&&<section className="results">
      <div className="results-head"><div><div className="eyebrow">CANDIDATE RANKING</div><h2>{job.title} <span>{rows.length}</span></h2></div><div className="results-actions"><div className="method">Skills 50% · Semantic 25% · Experience 15% · Education 10%</div><button type="button" className="reanalyze-button" disabled={reanalyzing||!rows.length} onClick={reanalyzeSavedCandidates}>{reanalyzing?<LoaderCircle className="spin" size={13}/>:null}{reanalyzing?'Reanalyzing…':'Refresh saved scores'}</button></div></div>
      <div className="ranking-stats"><div><span>Shortlisted candidates</span><b>{rows.length}</b></div><div><span>Top match</span><b>{rows[0]?`${rows[0].overall_score}%`:'—'}</b></div><div><span>Average score</span><b>{rows.length?`${averageScore}%`:'—'}</b></div></div>
      <div className="table-toolbar"><span>Ranked by match score · Refreshes automatically</span><label><span className="sr-only">Search candidates</span><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search by name or skill"/></label></div>
      {!rows.length?<div className="empty horizontal">No candidates yet. Upload resumes to build this shortlist.</div>:!visibleRows.length?<div className="empty horizontal">No candidates match “{search}”.</div>:<div className="table-wrap"><table><thead><tr><th>RANK</th><th>CANDIDATE</th><th>EXPERIENCE</th><th>SKILLS MATCHED</th><th>MATCH SCORE</th><th>RESUME</th><th></th></tr></thead><tbody>{visibleRows.map(r=><tr key={r.id} onClick={()=>inspect(r)}><td><span className="rank">{String(rows.findIndex(x=>x.id===r.id)+1).padStart(2,'0')}</span></td><td><b>{r.name||r.filename.replace(/\.(pdf|docx)$/i,'')}</b><small>{r.filename}</small></td><td>{r.experience_years===null?'Not listed':`${r.experience_years} yrs`}</td><td><div className="tags">{r.matched_skills.slice(0,3).map(s=><span key={s}>{s}</span>)}{r.matched_skills.length>3&&<span>+{r.matched_skills.length-3}</span>}</div></td><td><div className="score"><b className={scoreColor(r.overall_score)}>{r.overall_score}%</b><div><i className={scoreColor(r.overall_score)} style={{width:`${r.overall_score}%`}}/></div></div></td><td><button className="view-resume-button" type="button" onClick={e=>{e.stopPropagation();inspect(r,true);}}><Eye size={13}/>View</button></td><td><ChevronRight size={17}/></td></tr>)}</tbody></table></div>}
    </section>}
    <footer>TalentLens · Candidate scores use job-relevant information only.</footer>
    {selected&&<div className="overlay" onClick={()=>setSelected(null)}><article className="analysis-modal" role="dialog" aria-modal="true" aria-label={`${showResume?'Resume':'Candidate analysis'} for ${selected.name||selected.filename}`} onClick={e=>e.stopPropagation()}>
      <button className="close" onClick={()=>setSelected(null)} aria-label="Close candidate analysis"><X/></button>
      <div className="analysis-content">
      <div className="analysis-head"><div><div className="eyebrow">CANDIDATE ANALYSIS</div><h2>{selected.name||selected.filename}</h2><p className="muted">{selected.experience_years===null?'Experience not found':`${selected.experience_years} years of experience`}</p></div><div className="analysis-score"><b>{selected.overall_score}%</b><span>overall match</span></div></div>
      <div className="analysis-tabs"><button className={!showResume?'active':''} onClick={()=>setShowResume(false)}>Analysis</button><button className={showResume?'active':''} onClick={()=>setShowResume(true)}><Eye size={14}/>Resume file</button></div>
      {showResume?<><h3>Original resume · {selected.filename}</h3>{!selected.has_original_file?<div className="resume-download"><FileText size={24}/><span>This resume was saved before original-file viewing was added.</span><small>Re-upload the same file to attach its original document; it will update the saved candidate.</small></div>:/\.pdf$/i.test(selected.filename)?<iframe className="resume-pdf" title={`Original resume for ${selected.name||selected.filename}`} src={`/api/candidates/${selected.id}/resume`}/>:<div className="resume-download"><FileText size={24}/><span>DOCX files cannot be previewed in this browser.</span><a href={`/api/candidates/${selected.id}/resume`}>Download original resume</a></div>}</>:<>
      <h3>Score breakdown</h3>
      {Object.entries(selected.scores).filter(([k])=>k!=='weights').map(([k,v])=><div className={`breakdown ${v===null?'not-applicable':''}`} key={k}><span>{k}</span><b>{v===null?'N/A':`${v}%`}</b>{v!==null&&<i><i style={{width:`${v}%`}}/></i>}<small className="breakdown-reason">{scoreReason(k,v,selected)}</small></div>)}
      <h3>Required skills</h3><div className="tags large">{selected.matched_skills.map(s=><span className="matched" key={s}>✓ {s}</span>)}{selected.missing_skills.map(s=><span className="missing" key={s}>− {s}</span>)}</div>
      <h3>Why each skill matched</h3>
      <div className="requirement-reasons">{skillReasons.length?skillReasons.map(({skill,matched})=><div className={`requirement-reason ${matched?'is-matched':'is-missing'}`} key={skill}><span className="reason-status">{matched?'Matched':'Missing'}</span><b>{skill}</b><p>{matched?(selected.evidence?.[skill]||'Skill detected in resume text; no concise excerpt was available.'):'No supporting mention was found in the extracted resume text.'}</p></div>):<p className="empty-note">No required skills were extracted from this role.</p>}</div>
      <p className="explanation">{selected.explanation}</p>
      <h3>Employment history</h3>
      <div className="analysis-list">{selected.employment.length?selected.employment.map((item,i)=><p className="evidence-card" key={i}><span className="evidence-icon">W</span><span>{item}</span></p>):<p className="empty-note">No employment history was identified in this resume.</p>}</div>
      <h3>Projects</h3>
      <div className="analysis-list">{selected.projects.length?selected.projects.map((item,i)=>{const project=projectParts(item);return <article className="project-evidence" key={i}><div className="project-evidence-title"><span className="evidence-icon">P</span><h4>{project.title||'Project'}</h4></div>{project.details?.length>0&&<ul>{project.details.map((detail,n)=><li key={n}>{detail}</li>)}</ul>}{project.tools?.length>0&&<div className="project-tools">{project.tools.map(tool=><span key={tool}>{tool}</span>)}</div>}{project.links?.length>0&&<div className="project-links">{project.links.map((link,n)=>link.url?<a key={n} href={link.url} target="_blank" rel="noreferrer">{link.label} ↗</a>:<span key={n}>{link.label} listed</span>)}</div>}</article>}):<p className="empty-note">No projects were identified in this resume.</p>}</div>
      <h3>Education</h3>
      <div className="analysis-list">{(selected.education_records||[]).length?(selected.education_records||[]).map((record,i)=><article className="education-record" key={i}><span className="evidence-icon">E</span><div><h4>{record.qualification||record.institution||record.details[0]}</h4>{record.institution&&record.institution!==record.qualification&&<p>{record.institution}</p>}<div className="education-meta">{record.period&&<span>{record.period}</span>}{record.result&&<span>{record.result}</span>}</div>{record.details.filter(line=>![record.qualification,record.institution,record.period,record.result].includes(line)).length>0&&<small>{record.details.filter(line=>![record.qualification,record.institution,record.period,record.result].includes(line)).join(' · ')}</small>}</div></article>):<p className="empty-note">No education details were identified in this resume.</p>}</div>
      <h3>Skill evidence</h3>
      <div className="skill-evidence-list">{Object.entries(selected.evidence).map(([skill,evidence])=><div className="skill-evidence" key={skill}><b>{skill}</b><span>{evidence||'Skill listed in resume'}</span></div>)}</div>
      </>}
      </div>
    </article></div>}
  </main>
}
createRoot(document.getElementById('root')).render(<App/>);
