import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import * as XLSX from "npm:xlsx";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const ANTHROPIC_KEY = Deno.env.get("ANTHROPIC_API_KEY") || "";
const GREEN_INSTANCE = "7105301719";
const GREEN_TOKEN = "2ed49585655e49169428bcbc2151146779e7835b208d45cdbf";
const ALLOWED_PHONES = ["972502671012", "972502075696"];

const FIELD_ALIASES: Record<string,string> = {
  "שם": "name", "שם המענה":"name",
  "קטגוריה":"category",
  "תת קטגוריה":"subcategory","תת-קטגוריה":"subcategory",
  "תיאור":"description","פירוט":"description",
  "אזור":"geographic_area","מיקום":"geographic_area","אזור גיאוגרפי":"geographic_area",
  "מיקום מדויק":"location",
  "טלפון":"phone",
  "מייל":"email","אימייל":"email",
  "קישור":"url","אתר":"url",
  "גיל":"age_range",
  "אוכלוסייה":"target_population",
  "מסלול":"age_track","מסלול גיל":"age_track","טווח גיל":"age_track",
};
const FIELD_LABELS: Record<string,string> = {
  name:"שם המענה",category:"קטגוריה",subcategory:"תת קטגוריה",
  description:"תיאור",geographic_area:"אזור גיאוגרפי",location:"מיקום מדויק",phone:"טלפון",
  email:"מייל",url:"קישור",age_range:"גיל",target_population:"אוכלוסייה",
  age_track:"מסלול גיל (1418/1826)",
};

const TEXT_TYPES = ["textMessage", "extendedTextMessage"];

const supabase = createClient(SUPABASE_URL, SUPABASE_KEY);

async function send(chatId: string, msg: string) {
  try {
    const r = await fetch(`https://api.green-api.com/waInstance${GREEN_INSTANCE}/sendMessage/${GREEN_TOKEN}`,
      {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({chatId,message:msg})});
    console.log("Green API:", r.status, (await r.text()).substring(0,120));
  } catch(e){console.error("send error:",String(e));}
}

async function getCategories(): Promise<string[]> {
  const {data} = await supabase.from("programs").select("category").not("category","is",null);
  return [...new Set((data??[]).map((r:Record<string,string>)=>r.category).filter(Boolean))] as string[];
}

async function checkDup(name:string) {
  if(!name) return null;
  const {data} = await supabase.from("programs").select("id,name").ilike("name",name.trim()).limit(1);
  return data?.[0]??null;
}

type P = Record<string,string|null>;

function guessMime(fileName:string, rawMime:string):string {
  if(rawMime && rawMime!=="application/octet-stream") return rawMime;
  const l=fileName.toLowerCase();
  if(l.endsWith(".jpg")||l.endsWith(".jpeg")) return "image/jpeg";
  if(l.endsWith(".png")) return "image/png";
  if(l.endsWith(".webp")) return "image/webp";
  if(l.endsWith(".pdf")) return "application/pdf";
  if(l.endsWith(".xlsx")||l.endsWith(".xls")) return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  if(l.endsWith(".csv")) return "text/csv";
  if(l.match(/^[0-9a-f-]{36}(\.[a-z]+)?$/i)) return "image/jpeg";
  return rawMime||"image/jpeg";
}

async function parseWithClaude(content:unknown[]):Promise<P> {
  const PROMPT=`אתה עוזר לארגון הופה לקטלג מענים.
הופה פועלת בשני מסלולים: 14-18 (מניעת נשירה בבתי ספר) ו-18-26 (ליווי בוגרים).

קטגוריות מאושרות:
- שירות צבאי/לאומי (תת: מכינות ושנת שירות, חיילים בודדים, מנטורים במהלך הצבא, התנדבות לצה"ל)
- השכלה ופיתוח קריירה (תת: מלגות לימודים, לימודי יג-יד, מרכזי צעירים, הכוונה תעסוקתית, הנדסאים ועתודאים, השלמת בגרויות, העשרה וחוגים, פתיחת עסק, הכוונה לימודית)
- זכויות, דיור וסיוע כלכלי (תת: סיוע כלכלי ודיור, הלנת חירום, זכויות חיילים משוחררים, סיוע משפטי ומיצוי זכויות, דיור מוגן/דיור תומך, ציוד מחשוב)
- חוסן ותמיכה רגשית (תת: סיוע רפואי ורגשי, טיפול בהתמכרויות, מנטורים לחיים, טרום הורות, מוגנות, מסגרות חלופיות, חווה טיפולית)
- אוכלוסיות יעד מגוונות (תת: קהילה אתיופית, חרבות ברזל, קהילה להט"בית, יוצאי החברה החרדית)
- תעסוקה והכשרה מקצועית (תת: הכשרות תעסוקה, ליווי תעסוקתי, תכניות מעבר לאחר שירות צבאי, השמה והזדמנויות עבודה בחו"ל)

אזורים גיאוגרפיים: ארצי, ירושלים, מרכז, צפון, דרום

חלץ מידע והחזר JSON בלבד:
{"name":"שם המענה","category":"קטגוריה","subcategory":"תת-קטגוריה","phone":"טלפון","email":"אימייל","url":"קישור","description":"תיאור","target_population":"אוכלוסיית יעד","age_range":"גיל","location":"מיקום מדויק","geographic_area":"אזור גיאוגרפי (ארצי/ירושלים/מרכז/צפון/דרום)","contact_person":"איש קשר","service_type":"סוג שירות","age_track":"1418 או 1826 — אם המענה לבני נוער/בית ספר/נשירה: 1418, אחרת: 1826"}
שדות ללא מידע יקבלו null. age_track חייב להיות "1418" או "1826". category ו-subcategory חייבים להיות מהרשימה. geographic_area חייב להיות מהרשימה. JSON בלבד.`;
  try {
    const r=await fetch("https://api.anthropic.com/v1/messages",{
      method:"POST",
      headers:{"x-api-key":ANTHROPIC_KEY,"anthropic-version":"2023-06-01","content-type":"application/json"},
      body:JSON.stringify({model:"claude-sonnet-4-6",max_tokens:1024,
        messages:[{role:"user",content:[...content,{type:"text",text:PROMPT}]}]}),
    });
    const d=await r.json();
    console.log("Claude:",r.status,JSON.stringify(d).substring(0,200));
    if(!r.ok) return {};
    const raw=d?.content?.[0]?.text??"";
    const m=raw.match(/\{[\s\S]*\}/);
    return m?JSON.parse(m[0]):{};
  } catch(e){console.error("Claude err:",String(e));return {};}
}

function ageTrackLabel(t:string|null|undefined):string {
  if(t==="1418") return "14-18";
  if(t==="1826") return "18-26";
  return "18-26";
}

function confirmMsg(p:P):string {
  const lines=[
    `✅ *${p.name||"מענה חדש"}*`,
    `${p.category||"—"} ${p.subcategory?"· "+p.subcategory:""} · גיל ${ageTrackLabel(p.age_track)}`,
  ];
  if(p.description) lines.push(`${p.description.substring(0,120)}${p.description.length>120?"...":""}`);
  const details=[];
  if(p.geographic_area) details.push(`🗺️ ${p.geographic_area}`);
  if(p.location) details.push(`📍 ${p.location}`);
  if(p.phone) details.push(`📞 ${p.phone}`);
  if(p.url) details.push(`🔗 ${p.url}`);
  if(details.length) lines.push(details.join("  "));
  lines.push(``);
  lines.push(`לשמור? *כן* / *לא* — או כתבי מה לתקן`);
  return lines.join("\n");
}

async function interpretCorrection(text:string, current:P):Promise<P> {
  const PROMPT=`המשתמש רוצה לתקן פרטים על מענה.
נתונים נוכחיים: ${JSON.stringify(current)}
הודעה: "${text}"
החזר JSON עם רק השדות לעדכון מתוך: name, category, subcategory, description, location, phone, email, url, age_range, target_population, age_track.
age_track: "1418" ל-14-18, "1826" ל-18-26.
אם אין תיקון ברור, החזר {}.
JSON בלבד.`;
  try {
    const r=await fetch("https://api.anthropic.com/v1/messages",{
      method:"POST",
      headers:{"x-api-key":ANTHROPIC_KEY,"anthropic-version":"2023-06-01","content-type":"application/json"},
      body:JSON.stringify({model:"claude-sonnet-4-6",max_tokens:512,
        messages:[{role:"user",content:[{type:"text",text:PROMPT}]}]}),
    });
    const d=await r.json();
    if(!r.ok) return {};
    const raw=d?.content?.[0]?.text??"";
    const m=raw.match(/\{[\s\S]*\}/);
    return m?JSON.parse(m[0]):{};
  } catch(e){console.error("correction err:",String(e));return {};}
}

async function savePending(phone:string,chatId:string,raw:string,data:P,state:string){
  await supabase.from("whatsapp_pending").delete().eq("sender_phone",phone);
  await supabase.from("whatsapp_pending").insert({sender_phone:phone,chat_id:chatId,raw_message:raw,parsed_data:data,state});
}

async function saveProgram(p:P){
  const age_track = (p.age_track==="1418"||p.age_track==="1826") ? p.age_track : "1826";
  await supabase.from("programs").insert({
    name:p.name||"מענה מווטסאפ",description:p.description,
    category:p.category,subcategory:p.subcategory,
    target_population:p.target_population,age_range:p.age_range,
    url:p.url,phone:p.phone,email:p.email,
    contact_person:p.contact_person,location:p.location,
    geographic_area:p.geographic_area||"ארצי",
    service_type:p.service_type,status:"active",notes:"נוסף דרך ווטסאפ",
    age_track,
  });
}

function b64(buf:ArrayBuffer):string{
  const b=new Uint8Array(buf);let s="";
  for(let i=0;i<b.byteLength;i++)s+=String.fromCharCode(b[i]);
  return btoa(s);
}

function extractText(msgType:string, msgData:Record<string,unknown>):string {
  if(msgType==="textMessage")
    return String((msgData.textMessageData as Record<string,unknown>)?.textMessage??"");
  if(msgType==="extendedTextMessage")
    return String((msgData.extendedTextMessageData as Record<string,unknown>)?.text??"");
  return "";
}

async function buildClaudeContent(msgType:string,msgData:Record<string,unknown>):Promise<{content:unknown[],raw:string}>{
  if(TEXT_TYPES.includes(msgType)){
    const text=extractText(msgType,msgData);
    console.log("Text msg type:",msgType,"text[:80]:",text.substring(0,80));
    return {content:[{type:"text",text}],raw:text};
  }
  if(msgType==="documentMessage"||msgType==="imageMessage"){
    const fd=msgData.fileMessageData as Record<string,unknown>;
    const dlUrl=String(fd?.downloadUrl??"");
    const rawMime=String(fd?.mimeType??"");
    const caption=String(fd?.caption??"");
    const fileName=String(fd?.fileName??"");
    const mime=guessMime(fileName,rawMime);
    console.log("File:",fileName,"mime:",mime);
    if(dlUrl){
      try{
        const buf=await(await fetch(dlUrl)).arrayBuffer();
        const b64data=b64(buf);
        if(mime==="application/pdf")
          return {content:[{type:"document",source:{type:"base64",media_type:"application/pdf",data:b64data}},...(caption?[{type:"text",text:caption}]:[])],raw:caption||fileName};
        if(mime.startsWith("image/")){
          const im=["image/jpeg","image/png","image/gif","image/webp"].includes(mime)?mime:"image/jpeg";
          return {content:[{type:"image",source:{type:"base64",media_type:im,data:b64data}},...(caption?[{type:"text",text:caption}]:[])],raw:caption||fileName};
        }
        if(mime.includes("spreadsheet")||mime.includes("excel")||fileName.match(/\.xlsx?$/i)){
          const wb=XLSX.read(new Uint8Array(buf),{type:"array"});
          const sheets=wb.SheetNames.map((n:string)=>`${n}:\n${XLSX.utils.sheet_to_csv(wb.Sheets[n]).substring(0,4000)}`);
          return {content:[{type:"text",text:`Excel:\n${sheets.join("\n")}`},...(caption?[{type:"text",text:caption}]:[])],raw:caption||fileName};
        }
        if(mime==="text/csv"){
          const txt=new TextDecoder().decode(new Uint8Array(buf)).substring(0,6000);
          return {content:[{type:"text",text:txt}],raw:caption||fileName};
        }
      } catch(e){console.error("file err:",String(e));}
    }
    return {content:caption?[{type:"text",text:caption}]:[],raw:caption||fileName};
  }
  return {content:[],raw:""};
}

Deno.serve(async(req:Request)=>{
  if(req.method!=="POST") return new Response("OK",{status:200});
  let body:Record<string,unknown>;
  try{body=await req.json();}catch{return new Response("Bad request",{status:400});}
  if(body.typeWebhook!=="incomingMessageReceived")
    return new Response(JSON.stringify({ok:true}),{headers:{"Content-Type":"application/json"}});

  const msgData=body.messageData as Record<string,unknown>;
  const senderData=body.senderData as Record<string,unknown>;
  const chatId=String(senderData?.chatId??senderData?.sender??"");
  const phone=chatId.replace(/@.+$/,"");
  const msgType=String(msgData?.typeMessage??"");

  if(!ALLOWED_PHONES.includes(phone)){
    console.log("Ignored:",phone,"type:",msgType);
    return new Response(JSON.stringify({ok:true}),{headers:{"Content-Type":"application/json"}});
  }
  console.log("MSG:",msgType,"from:",phone);

  const {data:pending}=await supabase.from("whatsapp_pending").select("*")
    .eq("sender_phone",phone).order("created_at",{ascending:false}).limit(1).single();
  const state=pending?.state??null;
  const pd=(pending?.parsed_data??{}) as P;

  if(TEXT_TYPES.includes(msgType) && state){
    const text=extractText(msgType,msgData).trim();
    const YES_WORDS=["כן","yes","ok","אוקיי","בסדר","שמרי","שמור","מאשר","מאשרת","יאללה","אחלה","טוב","נראה טוב","נראה בסדר","סבבה","👍"];
    const NO_WORDS=["לא","no","בטל","ביטול","לבטל","עצור","מחק"];
    const tl=text.toLowerCase().trim();
    const yes=YES_WORDS.some(w=>tl===w.toLowerCase());
    const no=NO_WORDS.some(w=>tl===w.toLowerCase());
    console.log("Text cmd:",JSON.stringify(text),"state:",state);

    if(state==="edit_field"){
      const fk=pd._editing_field as string;
      if(fk){
        let val=text;
        if(fk==="age_track"){
          if(text.includes("14")||text==="נשירה"||text==="בית ספר") val="1418";
          else val="1826";
        }
        const upd={...pd,[fk]:val};
        delete upd._editing_field;
        await supabase.from("whatsapp_pending").update({state:"confirm_program",parsed_data:upd}).eq("id",pending.id);
        await send(chatId,confirmMsg(upd));
      }
      return new Response(JSON.stringify({ok:true}),{headers:{"Content-Type":"application/json"}});
    }

    if(state==="confirm_category"){
      if(yes){
        await supabase.from("whatsapp_pending").update({state:"confirm_program"}).eq("id",pending.id);
        await send(chatId,confirmMsg(pd));
      } else if(no){
        await supabase.from("whatsapp_pending").update({state:"input_category"}).eq("id",pending.id);
        const cats=await getCategories();
        await send(chatId,`באיזו קטגוריה?\n\nקיימות:\n${cats.slice(0,20).join(" | ")}\n\nכתבי:`);
      } else {
        await send(chatId,"עני *כן* או *לא*.");
      }
      return new Response(JSON.stringify({ok:true}),{headers:{"Content-Type":"application/json"}});
    }

    if(state==="input_category"){
      const upd={...pd,category:text};
      await supabase.from("whatsapp_pending").update({state:"confirm_program",parsed_data:upd}).eq("id",pending.id);
      await send(chatId,confirmMsg(upd));
      return new Response(JSON.stringify({ok:true}),{headers:{"Content-Type":"application/json"}});
    }

    if(state==="confirm_duplicate"){
      if(yes){
        await saveProgram(pd);
        await supabase.from("whatsapp_pending").delete().eq("id",pending.id);
        await send(chatId,`✅ *${pd.name||"מענה"}* נשמר (כולל כפיל)!`);
      } else if(no){
        await supabase.from("whatsapp_pending").delete().eq("id",pending.id);
        await send(chatId,"בוטל.");
      } else { await send(chatId,"עני *כן* או *לא*."); }
      return new Response(JSON.stringify({ok:true}),{headers:{"Content-Type":"application/json"}});
    }

    if(state==="confirm_program"){
      if(yes){
        const dup=await checkDup(pd.name??"");
        if(dup){
          await supabase.from("whatsapp_pending").update({state:"confirm_duplicate"}).eq("id",pending.id);
          await send(chatId,`⚠️ קיים כבר *${dup.name}* (ID ${dup.id}).\nלשמור בכל זאת? *כן* / *לא*`);
        } else {
          await saveProgram(pd);
          await supabase.from("whatsapp_pending").delete().eq("id",pending.id);
          await send(chatId,`✅ *${pd.name||"מענה"}* נשמר!`);
        }
        return new Response(JSON.stringify({ok:true}),{headers:{"Content-Type":"application/json"}});
      }
      if(no){
        await supabase.from("whatsapp_pending").delete().eq("id",pending.id);
        await send(chatId,"בוטל. שלחי מענה חדש.");
        return new Response(JSON.stringify({ok:true}),{headers:{"Content-Type":"application/json"}});
      }
      // תיקון חופשי — Claude מפרש
      const correction=await interpretCorrection(text,pd);
      if(Object.keys(correction).length>0){
        const upd={...pd,...correction};
        await supabase.from("whatsapp_pending").update({parsed_data:upd}).eq("id",pending.id);
        await send(chatId,confirmMsg(upd));
      } else {
        await send(chatId,`לא הבנתי 🤔\nלשמור? *כן* / *לא* — או כתבי מה לתקן (לדוגמא: "הקישור הוא xyz.com" / "זה למסלול 14-18")`);
      }
      return new Response(JSON.stringify({ok:true}),{headers:{"Content-Type":"application/json"}});
    }
  }

  const {content,raw}=await buildClaudeContent(msgType,msgData);
  if(!content.length){
    const handled=TEXT_TYPES.includes(msgType)||msgType==="documentMessage"||msgType==="imageMessage";
    if(handled) await send(chatId,"לא הצלחתי לקרוא את התוכן.");
    else console.log("Unhandled msg type:",msgType);
    return new Response(JSON.stringify({ok:true}),{headers:{"Content-Type":"application/json"}});
  }

  const parsed=await parseWithClaude(content);
  if(!parsed.name){
    await send(chatId,"לא זיהיתי מענה בתוכן. נסי לשלוח עם פרטים ברורים יותר.");
    return new Response(JSON.stringify({ok:true}),{headers:{"Content-Type":"application/json"}});
  }

  const cats=await getCategories();
  const cat=parsed.category;
  const catOk=!cat||cats.some(c=>c.trim().toLowerCase()===cat.trim().toLowerCase());

  if(!catOk){
    await savePending(phone,chatId,raw,parsed,"confirm_category");
    await send(chatId,`❓ הקטגוריה *${cat}* לא קיימת עדיין.\nליצור חדשה? *כן* / *לא*`);
  } else {
    await savePending(phone,chatId,raw,parsed,"confirm_program");
    await send(chatId,confirmMsg(parsed));
  }

  return new Response(JSON.stringify({ok:true}),{headers:{"Content-Type":"application/json"},status:200});
});
