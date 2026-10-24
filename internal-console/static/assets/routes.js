export function matchWorkflowRoute(path) {
  const excelImportMatch=path.match(/^\/cases\/excel-imports\/(import_[a-f0-9]{32})$/);
  if(excelImportMatch)return {name:'excel-import-result',value:excelImportMatch[1]};
  const intakeMatch = path.match(/^\/case-intake\/(intake-[a-f0-9]{32})$/);
  if (intakeMatch) return { name: "case-intake", value: intakeMatch[1] };
  const classificationMatch = path.match(/^\/cases\/(\d{10,24})\/classification$/);
  if (classificationMatch) return { name: "case-classification", value: classificationMatch[1] };
  const caseMatch = path.match(
    /^\/cases\/(\d{10,24})$/,
  );

  if (caseMatch) {
    return {
      name: "case-detail",
      value: caseMatch[1],
    };
  }

  const speakerNewMatch = path.match(
    /^\/customers\/([a-z0-9][a-z0-9_]{1,127})\/speakers\/new$/,
  );

  if (speakerNewMatch) {
    return {
      name: "speaker-new",
      businessId: speakerNewMatch[1],
    };
  }

  const speakerSupplementMatch = path.match(
    /^\/customers\/([a-z0-9][a-z0-9_]{1,127})\/speakers\/([a-z0-9][a-z0-9_-]{1,127})\/supplement$/,
  );

  if (speakerSupplementMatch) {
    return {
      name: "speaker-supplement",
      businessId: speakerSupplementMatch[1],
      speakerId: speakerSupplementMatch[2],
    };
  }

  const speakerDetailMatch = path.match(
    /^\/customers\/([a-z0-9][a-z0-9_]{1,127})\/speakers\/([a-z0-9][a-z0-9_-]{1,127})$/,
  );

  if (speakerDetailMatch) {
    return {
      name: "speaker-detail",
      businessId: speakerDetailMatch[1],
      speakerId: speakerDetailMatch[2],
    };
  }

  const customerContentOperationsMatch =
    path.match(
      /^\/customers\/([a-z0-9][a-z0-9_]{1,127})\/content$/,
    );

  if (customerContentOperationsMatch) {
    return {
      name: "customer-content-operations",
      value:
        customerContentOperationsMatch[1],
    };
  }

  const customerEditMatch = path.match(
    /^\/customers\/([a-z0-9][a-z0-9_]{1,127})\/edit$/,
  );

  if (customerEditMatch) {
    return {
      name: "customer-edit",
      value: customerEditMatch[1],
    };
  }

  const customerSupplementMatch = path.match(
    /^\/customers\/([a-z0-9][a-z0-9_]{1,127})\/supplement$/,
  );

  if (customerSupplementMatch) {
    return {
      name: "customer-supplement",
      value: customerSupplementMatch[1],
    };
  }

  const customerMatch = path.match(
    /^\/customers\/([a-z0-9][a-z0-9_]{1,127})$/,
  );

  if (customerMatch) {
    return {
      name: "customer-detail",
      value: customerMatch[1],
    };
  }

  const taskMatch = path.match(
    /^\/tasks\/([A-Za-z0-9_-]+)$/,
  );

  if (taskMatch) {
    return {
      name: "task-detail",
      value: taskMatch[1],
    };
  }

  return null;
}

// Only this local workflow can retain a post-login destination.
export function safeExcelReturn(value){
  if(typeof value!=='string' || value.length>512 || !value.startsWith('/') || value.startsWith('//') || value.includes('\\'))return null;
  try{
    const url=new URL(value,'http://local.invalid');if(url.origin!=='http://local.invalid')return null;
    const path=url.pathname.replace(/\/+$/,'');const result=matchWorkflowRoute(path)?.name==='excel-import-result';
    if(!result && !['/cases/excel-preview','/cases/excel-imports'].includes(path))return null;
    const query=new URLSearchParams();
    if(result){const op=url.searchParams.get('operation');if(op && /^[a-z][a-z0-9_-]{1,127}$/.test(op))query.set('operation',op);if(url.searchParams.get('view')==='cases')query.set('view','cases');}
    if(path==='/cases/excel-imports' && /^[1-9][0-9]{0,5}$/.test(url.searchParams.get('page') || ''))query.set('page',url.searchParams.get('page'));
    return path+(query.size?'?'+query:'');
  }catch{return null;}
}
export function excelLoginPath(value){const back=safeExcelReturn(value);return back?'/login?return_to='+encodeURIComponent(back):'/login';}
