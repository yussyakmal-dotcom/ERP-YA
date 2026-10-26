async function csvDownload(name, kind) {
 const r=await fetch('/api/master-csv/'+name+'/'+kind);if(!r.ok){throw Error((await r.json()).detail)}
 const a=el('a',{href:URL.createObjectURL(await r.blob()),download:name+'-'+kind+'.csv'});a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);
}
async function csvImport(name) {
 const box=el('div');box.append(el('p',{textContent:'Unggah CSV UTF-8. Aksi: CREATE, UPDATE, NEW_VERSION, DEACTIVATE atau DELETE. Kolom kosong mempertahankan nilai lama; __NULL__ mengosongkan kolom opsional. Semua baris harus valid sebelum diterapkan.'}));
 const file=el('input',{type:'file',accept:'.csv,text/csv'}),status=el('div'),apply=button('Terapkan impor',async()=>{apply.disabled=true;try{const r=await api('/master-csv/'+name+'/apply',{method:'POST',body:JSON.stringify({preview_id:previewId})});status.textContent='Impor berhasil: '+JSON.stringify(r.summary);cache={};}catch(e){status.textContent=e.message}} ,true);
 let previewId=null;apply.disabled=true;
 const check=button('Periksa file',async()=>{apply.disabled=true;previewId=null;try{if(!file.files[0])throw Error('Pilih file CSV terlebih dahulu');const r=await api('/master-csv/'+name+'/preview',{method:'POST',headers:{'Content-Type':'text/csv'},body:await file.files[0].text()});previewId=r.preview_id;status.replaceChildren(el('p',{textContent:JSON.stringify(r.summary)}));for(const row of r.rows){status.append(el('p',{textContent:'Baris '+row.line+' · '+row.key+' · '+row.operation+(row.error?' · '+row.error:'')}));if(row.changes.length)status.append(el('pre',{textContent:JSON.stringify(row.changes,null,2)}))}apply.disabled=!r.valid;}catch(e){status.textContent=e.message}});
 file.onchange=()=>{previewId=null;apply.disabled=true;status.textContent='Periksa file sebelum diterapkan.'};box.append(file,check,status,apply);modal('Impor CSV · '+(names[name]||name),box);
}
