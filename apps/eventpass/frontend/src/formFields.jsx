import React,{useEffect,useRef,useState} from 'react';
// Google-Forms-style registration fields: builder for admins, renderer for the public form.
export const FIELD_TYPES=[['text','Kurze Antwort'],['textarea','Absatz'],['select','Dropdown'],['radio','Auswahl (eine Antwort)'],['checkbox','Kästchen (mehrere Antworten)'],['number','Zahl'],['email','E-Mail'],['phone','Telefon'],['date','Datum']];
const CHOICE=['select','radio','checkbox'];
export const blankField=()=>({label:'',type:'text',required:false,options:[],help:''});
// Drops empty options/fields before sending; the server validates again.
export function cleanFields(fields){return fields.filter(f=>f.label.trim()).map(f=>({...f,label:f.label.trim(),options:CHOICE.includes(f.type)?(f.options||[]).map(o=>o.trim()).filter(Boolean):[]}))}

export function FieldBuilder({fields,onChange}){
 const set=(i,patch)=>onChange(fields.map((f,j)=>j===i?{...f,...patch}:f));
 const move=(i,d)=>{const n=[...fields];[n[i],n[i+d]]=[n[i+d],n[i]];onChange(n)};
 return <div className="field-builder">
  {!fields.length&&<p className="hint">Noch keine eigenen Felder. Name, E-Mail, Kategorie und Verpflegung werden immer abgefragt.</p>}
  {fields.map((f,i)=><div className="field-card" key={i}>
   <div className="two"><label>Frage<input value={f.label} maxLength={80} onChange={e=>set(i,{label:e.target.value})} placeholder="z. B. Gemeinde"/></label>
    <label>Antworttyp<select value={f.type||'text'} onChange={e=>set(i,{type:e.target.value})}>{FIELD_TYPES.map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label></div>
   {CHOICE.includes(f.type)&&<label>Optionen (eine pro Zeile)<textarea rows={Math.max(3,(f.options||[]).length+1)} value={(f.options||[]).join('\n')} onChange={e=>set(i,{options:e.target.value.split('\n')})} placeholder={'Option 1\nOption 2'}/></label>}
   <label>Hinweis unter der Frage (optional)<input value={f.help||''} maxLength={200} onChange={e=>set(i,{help:e.target.value})}/></label>
   <div className="field-actions"><label className="check"><input type="checkbox" checked={f.required} onChange={e=>set(i,{required:e.target.checked})}/> Pflichtfeld</label>
    <span><button type="button" className="secondary" disabled={!i} onClick={()=>move(i,-1)} aria-label="Nach oben">↑</button><button type="button" className="secondary" disabled={i===fields.length-1} onClick={()=>move(i,1)} aria-label="Nach unten">↓</button><button type="button" className="secondary" onClick={()=>onChange(fields.filter((_,j)=>j!==i))}>Entfernen</button></span></div>
  </div>)}
  <button type="button" className="secondary" disabled={fields.length>=30} onClick={()=>onChange([...fields,blankField()])}>+ Frage hinzufügen</button>
 </div>;
}

export function FieldInput({field:f,value,onChange}){
 const type=f.type||'text';const help=f.help&&<small className="hint">{f.help}</small>;const title=<>{f.label}{f.required?' *':''}</>;
 if(type==='radio'||type==='checkbox'){
  const picked=type==='checkbox'?(Array.isArray(value)?value:[]):value;
  const toggle=o=>onChange(picked.includes(o)?picked.filter(x=>x!==o):[...picked,o]);
  return <fieldset className="choice"><legend>{title}</legend>{help}{f.options.map(o=><label className="check" key={o}><input type={type} name={f.label} required={type==='radio'&&f.required} checked={type==='radio'?value===o:picked.includes(o)} onChange={()=>type==='radio'?onChange(o):toggle(o)}/> {o}</label>)}</fieldset>;
 }
 const props={required:f.required,value:value||'',onChange:e=>onChange(e.target.value)};
 return <label>{title}{help}{type==='textarea'?<textarea rows={4} maxLength={2000} {...props}/>:type==='select'?<select {...props}><option value="">Bitte wählen …</option>{f.options.map(o=><option key={o}>{o}</option>)}</select>:<input type={{phone:'tel',number:'text'}[type]||type} inputMode={type==='number'?'decimal':undefined} maxLength={300} {...props}/>}</label>;
}
// Required checkbox groups cannot be enforced by the browser.
export function missingRequired(fields,answers){return fields.find(f=>f.required&&f.type==='checkbox'&&!(answers[f.label]||[]).length)}

// Ready-to-send invitation for gate staff; editable before copying.
// The quick link fills in username and password on the gate page (the password sits after "#",
// which browsers never send to the server). Both values also stand alone on their own line,
// so a double tap selects exactly the value.
export function gateQuickLink(link,gate){return `${link}?u=${encodeURIComponent(gate.username)}#p=${encodeURIComponent(gate.password)}`}

export function gateMessage({lang,event,gate,link,dates}){
 const until=new Date(gate.expires_at).toLocaleString(lang==='de'?'de-DE':'en-GB',{dateStyle:'medium',timeStyle:'short'});
 const quick=gateQuickLink(link,gate);
 return lang==='de'?`Hallo ${gate.display_name},

du hilfst beim Check-in für „${event.title}“ (${dates}, ${event.location}). Danke!

1. Tippe auf diesen Link – Benutzername und Passwort sind schon eingetragen:
${quick}

2. Tippe auf „Anmelden“, dann auf „📷 QR-Code scannen“ und erlaube den Kamerazugriff. Dann einfach die Badges der Teilnehmer scannen.
${gate.can_add?`
Wer keinen Badge hat, kannst du direkt in der App als Teilnehmer hinzufügen.
`:''}
Falls du dich von Hand anmelden musst (${link}):

Benutzername:
${gate.username}

Passwort:
${gate.password}

Dein Zugang gilt bis ${until}. Bitte gib ihn nicht weiter.`:`Hello ${gate.display_name},

you are helping with check-in for "${event.title}" (${dates}, ${event.location}). Thank you!

1. Tap this link – your username and password are already filled in:
${quick}

2. Tap "Anmelden" (sign in), then "📷 QR-Code scannen" and allow camera access. Then simply scan the participants' badges.
${gate.can_add?`
If someone has no badge, you can add them as a participant directly in the app.
`:''}
If you need to sign in by hand (${link}):

Username:
${gate.username}

Password:
${gate.password}

Your access is valid until ${until}. Please do not share it.`;
}

async function copyText(text,el){
 try{await navigator.clipboard.writeText(text);return true}catch{} // clipboard API only exists on https/localhost
 el?.select();try{return document.execCommand('copy')}catch{return false}
}

export function GateInvite({event,gate,link,dates,onClose}){
 const [lang,setLang]=useState('de');const [text,setText]=useState('');const [copied,setCopied]=useState('');const area=useRef(null);
 useEffect(()=>{setText(gateMessage({lang,event,gate,link,dates}));setCopied('')},[lang,gate.username]);
 async function copy(){setCopied(await copyText(text,area.current)?'Kopiert ✓':'Bitte Text markieren und manuell kopieren')}
 async function copyValue(value,label){setCopied(await copyText(value)?`${label} kopiert ✓`:'Bitte markieren und manuell kopieren')}
 return <div className="notice checked_in gate-invite"><strong>Zugang erstellt – das Passwort ist nur jetzt sichtbar!</strong>
  <p>Diese Nachricht an {gate.display_name} schicken (z. B. per WhatsApp). Du kannst den Text vorher anpassen.</p>
  <label className="lang">Sprache<select value={lang} onChange={e=>setLang(e.target.value)}><option value="de">Deutsch</option><option value="en">English</option></select></label>
  <textarea ref={area} rows={18} value={text} onChange={e=>setText(e.target.value)} onFocus={e=>e.target.select()}/>
  <div className="credentials"><span>Benutzername <code>{gate.username}</code></span><button type="button" className="secondary small" onClick={()=>copyValue(gate.username,'Benutzername')}>Kopieren</button>
   <span>Passwort <code>{gate.password}</code></span><button type="button" className="secondary small" onClick={()=>copyValue(gate.password,'Passwort')}>Kopieren</button>
   <span>Ein-Tipp-Link</span><button type="button" className="secondary small" onClick={()=>copyValue(gateQuickLink(link,gate),'Link')}>Kopieren</button></div>
  <div className="toolbar"><button type="button" onClick={copy}>📋 Nachricht kopieren</button><a className="button secondary" href={`https://wa.me/?text=${encodeURIComponent(text)}`} target="_blank" rel="noreferrer">WhatsApp</a><a className="button secondary" href={`mailto:?subject=${encodeURIComponent('Check-in: '+event.title)}&body=${encodeURIComponent(text)}`}>E-Mail</a><button type="button" className="secondary" onClick={onClose}>Ausblenden</button>{copied&&<span className="hint">{copied}</span>}</div>
 </div>;
}
