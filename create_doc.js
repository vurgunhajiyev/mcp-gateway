"use strict";
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat, HeadingLevel,
  BorderStyle, WidthType, ShadingType, VerticalAlign,
  PageNumber, PageBreak
} = require("docx");

// ─── COLOR CONSTANTS ────────────────────────────────────────────────────────
const NAVY       = "1F3864";   // title / H1
const DARK_BLUE  = "2E5496";   // H2
const WHITE      = "FFFFFF";
const LIGHT_BLUE = "E8F0FB";   // alt row
const GRAY_TEXT  = "595959";

// ─── A4 in DXA  (1 inch = 1440 DXA) ─────────────────────────────────────────
// A4: 210mm × 297mm  →  11906 × 16838 DXA
const PAGE_W = 11906;
const PAGE_H = 16838;
const MARGIN  = 1134;  // ~2 cm each side
const CONTENT_W = PAGE_W - MARGIN * 2;  // 9638

// ─── CELL PADDING ────────────────────────────────────────────────────────────
const CELL_MARGINS = { top: 80, bottom: 80, left: 120, right: 120 };

// ─── BORDERS ─────────────────────────────────────────────────────────────────
function makeBorders(color = "C0C8D8") {
  const b = { style: BorderStyle.SINGLE, size: 4, color };
  return { top: b, bottom: b, left: b, right: b };
}

// ─── HELPER — plain paragraph ─────────────────────────────────────────────────
function para(text, opts = {}) {
  const runOpts = {
    text,
    font:  opts.font  || "Calibri",
    size:  opts.size  || 22,         // 11pt = 22 half-pts
    bold:  opts.bold  || false,
    italics: opts.italic || false,
    color: opts.color || undefined,
  };
  return new Paragraph({
    alignment: opts.align || AlignmentType.LEFT,
    spacing:   { before: opts.spaceBefore || 80, after: opts.spaceAfter || 80 },
    pageBreakBefore: opts.pageBreakBefore || false,
    children: [new TextRun(runOpts)],
  });
}

// ─── HELPER — heading 1 ──────────────────────────────────────────────────────
function h1(text, opts = {}) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    pageBreakBefore: opts.pageBreakBefore || false,
    spacing: { before: 280, after: 140 },
    children: [new TextRun({ text, font: "Calibri", size: 28, bold: true, color: NAVY })],
  });
}

// ─── HELPER — heading 2 ──────────────────────────────────────────────────────
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 220, after: 110 },
    children: [new TextRun({ text, font: "Calibri", size: 24, bold: true, color: DARK_BLUE })],
  });
}

// ─── HELPER — heading 3 ──────────────────────────────────────────────────────
function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 160, after: 80 },
    children: [new TextRun({ text, font: "Calibri", size: 22, bold: true })],
  });
}

// ─── HELPER — bullet item ─────────────────────────────────────────────────────
function bullet(text) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    spacing: { before: 40, after: 40 },
    children: [new TextRun({ text, font: "Calibri", size: 22 })],
  });
}

// ─── HELPER — spacer paragraph ───────────────────────────────────────────────
function spacer(pts = 4) {
  return new Paragraph({ spacing: { before: 0, after: pts * 10 }, children: [] });
}

// ─── HELPER — table cell ─────────────────────────────────────────────────────
function cell(text, opts = {}) {
  const isHeader = opts.header || false;
  const bgColor  = opts.bg || (isHeader ? NAVY : opts.altRow ? LIGHT_BLUE : WHITE);
  const textColor = isHeader ? WHITE : (opts.textColor || "000000");
  return new TableCell({
    width:   { size: opts.width || 4819, type: WidthType.DXA },
    borders: makeBorders(),
    shading: { fill: bgColor, type: ShadingType.CLEAR },
    margins: CELL_MARGINS,
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({
      spacing: { before: 20, after: 20 },
      children: [new TextRun({
        text,
        font:  "Calibri",
        size:  opts.size || 20,
        bold:  opts.bold || isHeader,
        color: textColor,
      })],
    })],
  });
}

// ─── HELPER — build a 2-column table ─────────────────────────────────────────
function table2(headers, rows, colWidths) {
  const [w1, w2] = colWidths || [3200, 6438];
  const totalW = w1 + w2;

  const headerRow = new TableRow({
    tableHeader: true,
    children: [
      cell(headers[0], { header: true, width: w1 }),
      cell(headers[1], { header: true, width: w2 }),
    ],
  });

  const dataRows = rows.map(([c1, c2], idx) => {
    const alt = idx % 2 === 1;
    return new TableRow({
      children: [
        cell(c1, { width: w1, altRow: alt }),
        cell(c2, { width: w2, altRow: alt }),
      ],
    });
  });

  return new Table({
    width: { size: totalW, type: WidthType.DXA },
    columnWidths: [w1, w2],
    rows: [headerRow, ...dataRows],
  });
}

// ─── HELPER — build a 3-column table ─────────────────────────────────────────
function table3(headers, rows, colWidths) {
  const [w1, w2, w3] = colWidths || [3500, 1800, 4338];
  const totalW = w1 + w2 + w3;

  const headerRow = new TableRow({
    tableHeader: true,
    children: [
      cell(headers[0], { header: true, width: w1 }),
      cell(headers[1], { header: true, width: w2 }),
      cell(headers[2], { header: true, width: w3 }),
    ],
  });

  const dataRows = rows.map(([c1, c2, c3], idx) => {
    const alt = idx % 2 === 1;
    return new TableRow({
      children: [
        cell(c1, { width: w1, altRow: alt }),
        cell(c2, { width: w2, altRow: alt }),
        cell(c3, { width: w3, altRow: alt }),
      ],
    });
  });

  return new Table({
    width: { size: totalW, type: WidthType.DXA },
    columnWidths: [w1, w2, w3],
    rows: [headerRow, ...dataRows],
  });
}

// ─── HELPER — build a 4-column table ─────────────────────────────────────────
function table4(headers, rows, colWidths) {
  const [w1, w2, w3, w4] = colWidths || [3000, 1700, 1700, 3238];
  const totalW = w1 + w2 + w3 + w4;

  const headerRow = new TableRow({
    tableHeader: true,
    children: [
      cell(headers[0], { header: true, width: w1 }),
      cell(headers[1], { header: true, width: w2 }),
      cell(headers[2], { header: true, width: w3 }),
      cell(headers[3], { header: true, width: w4 }),
    ],
  });

  const dataRows = rows.map(([c1, c2, c3, c4], idx) => {
    const alt = idx % 2 === 1;
    return new TableRow({
      children: [
        cell(c1, { width: w1, altRow: alt }),
        cell(c2, { width: w2, altRow: alt }),
        cell(c3, { width: w3, altRow: alt }),
        cell(c4, { width: w4, altRow: alt }),
      ],
    });
  });

  return new Table({
    width: { size: totalW, type: WidthType.DXA },
    columnWidths: [w1, w2, w3, w4],
    rows: [headerRow, ...dataRows],
  });
}

// ─── HELPER — build a 6-column table ─────────────────────────────────────────
function table6(headers, rows, colWidths) {
  const ws = colWidths || [2800, 1000, 1200, 1400, 1200, 2038];
  const totalW = ws.reduce((a, b) => a + b, 0);

  function mkCell(text, isHdr, altRow, w) {
    return cell(text, { header: isHdr, altRow, width: w, size: 18 });
  }

  const headerRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) => mkCell(h, true, false, ws[i])),
  });

  const dataRows = rows.map((row, idx) => {
    const alt = idx % 2 === 1;
    return new TableRow({
      children: row.map((c, i) => mkCell(c, false, alt, ws[i])),
    });
  });

  return new Table({
    width: { size: totalW, type: WidthType.DXA },
    columnWidths: ws,
    rows: [headerRow, ...dataRows],
  });
}

// ─── PAGE BREAK ───────────────────────────────────────────────────────────────
function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}

// ═══════════════════════════════════════════════════════════════════════════════
// DOCUMENT CONTENT
// ═══════════════════════════════════════════════════════════════════════════════

const children = [];

// ── COVER PAGE ────────────────────────────────────────────────────────────────
children.push(spacer(80));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 2400, after: 320 },
  children: [new TextRun({
    text: "TEXNOLOGIYA ŞİRKƏTİ ÜÇÜN DAXİLİ STAJ PROQRAMI",
    font: "Calibri", size: 44, bold: true, color: NAVY,
  })],
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 80, after: 160 },
  children: [new TextRun({
    text: "Proqram Nizamnaməsi və Strateji Sənəd",
    font: "Calibri", size: 26, color: GRAY_TEXT,
  })],
}));
children.push(spacer(40));
children.push(para("Sənəd Versiyası: v1.0 | Aprel 2026", { align: AlignmentType.CENTER, size: 22, color: GRAY_TEXT }));
children.push(para("Hazırlayanlar: HR Strategiya Departamenti | CTO Ofisi | Proqram İdarəetmə Komandası", { align: AlignmentType.CENTER, size: 22, color: GRAY_TEXT }));
children.push(para("Təsdiq: CEO / CTO imzası üçün hazırdır", { align: AlignmentType.CENTER, size: 22, color: GRAY_TEXT }));
children.push(pageBreak());

// ── SECTION 1 ─────────────────────────────────────────────────────────────────
children.push(h1("1. İCRAİ XÜLASƏSİ (EXECUTIVE SUMMARY)"));
children.push(para("Şirkətimiz qarşılaşdığı texniki kadr çatışmazlığı, bahalı xarici işə qəbul prosesləri və sürətlə dəyişən texnologiya ekosistemin tələbləri fonunda daxili Staj İnkişaf Proqramı (SİP) yaratmağı strateji prioritet kimi müəyyən etmişdir."));
children.push(para("Bu proqram 6-8 aylıq strukturlaşdırılmış öyrənmə, mentorluq və real layihə təcrübəsini birləşdirərək aşağıdakı sahələrdə gələcəyin mütəxəssislərini yetişdirməyi hədəfləyir:"));
children.push(bullet("Data Mühəndisliyi & Analitika"));
children.push(bullet("AI & Backend Mühəndisliyi"));
children.push(bullet("Biznes Analitikası & IT Layihə Koordinasiyası"));
children.push(spacer());
children.push(para("Proqramın Əsas Məqsədi: Xarici işə qəbuldan asılılığı azaltmaq, şirkətin mədəniyyətinə uyğun formada yetişdirilmiş gənc istedadlardan ibarət davamlı talent pipeline yaratmaq və AI adaptasiyasını sürətləndirmək."));
children.push(spacer(8));
children.push(new Paragraph({
  spacing: { before: 120, after: 60 },
  children: [new TextRun({ text: "Gözlənilən Əsas Nəticələr", font: "Calibri", size: 22, bold: true })],
}));
children.push(table2(
  ["Göstərici", "Hədəf"],
  [
    ["Proqram tamamlayan interns", "15-25 nəfər / il"],
    ["Full-time işə keçid faizi", ">= 60%"],
    ["Xarici işə qəbul xərclərinin azalması", "30-40%"],
    ["Layihəyə real töhfə faizi", ">= 80% intern"],
    ["Mentor məmnuniyyəti", ">= 4.2 / 5.0"],
  ],
  [5000, 4638]
));
children.push(pageBreak());

// ── SECTION 2 ─────────────────────────────────────────────────────────────────
children.push(h1("2. PROQRAM MƏQSƏDLƏRİ VƏ STRATEJİ HƏDƏFLƏRİ"));
children.push(h2("2.1 Strateji Əsaslandırma"));
children.push(para("Texnologiya sektorunda ixtisaslı kadr tapmaq getdikcə çətinləşir və bahalılaşır. Senior mütəxəssisin cəlb edilməsi xərcləri yüksək olduğu halda, daxili yetişdirilmiş kadrlar şirkətin dəyərlərinə, proseslərinə və texniki arxitekturasına daha dərindən inteqrasiya olur."));
children.push(h2("2.2 Strateji Hədəflər"));
children.push(h3("Biznes Hədəfləri:"));
children.push(bullet("Xarici işə qəbul xərclərini 30-40% azaltmaq"));
children.push(bullet("Şirkətin texnoloji innovasiya tempini artırmaq"));
children.push(bullet("Data-driven və AI-first mədəniyyətin gənc nəslə ötürülməsini təmin etmək"));
children.push(h3("İnsan Resursları Hədəfləri:"));
children.push(bullet("Şirkətin dəyərləri ilə yetişdirilmiş mütəxəssis hovuzu yaratmaq"));
children.push(bullet("Employer brand-i gücləndirib universitetlərdə tanınırlığı artırmaq"));
children.push(bullet("İşçi dövriyyəsini (turnover) azaltmaq"));
children.push(h3("Texniki Hədəflər:"));
children.push(bullet("AI alətlərinin komandalar arasında yayılmasını sürətləndirmək"));
children.push(bullet("Data mədəniyyəti və analitik düşüncənin inkişafı"));
children.push(bullet("Backend sistemlərə AI inteqrasiyasını genişləndirmək"));
children.push(h2("2.3 Uğur Meyarları"));
children.push(bullet("Proqramın 1-ci ilinin sonunda ən azı 12 intern uğurla mezun olur"));
children.push(bullet("Mezunların >= 60%-i şirkətdə full-time işə başlayır"));
children.push(bullet("Hər intern proqram ərzində ən azı 1 real biznes problemini həll edir"));
children.push(bullet("Proqram üzrə NPS (Net Promoter Score) >= 50 olur"));
children.push(pageBreak());

// ── SECTION 3 ─────────────────────────────────────────────────────────────────
children.push(h1("3. HƏDƏF NAMİZƏD PROFİLLƏRİ"));
children.push(h2("3.1 Ümumi Giriş Tələbləri"));
children.push(table2(
  ["Kateqoriya", "Tələb"],
  [
    ["Təhsil", "Ali təhsil (3-5-ci kurs) və ya yeni məzun (0-1 il iş təcrübəsi)"],
    ["Dil", "Azərbaycan / Rus (iş dili); İngilis dili (B1+)"],
    ["Öyrənmə iştahı", "Yüksək motivasiya, özünüidarəetmə qabiliyyəti"],
    ["Texniki baza", "İxtisasa görə dəyişir"],
  ],
  [3200, 6438]
));
children.push(spacer(8));
children.push(h2("3.2 Data Track — Data Engineer & Data Analyst"));
children.push(h3("Data Engineer Namizədi:"));
children.push(bullet("Təhsil: Kompüter elmləri, riyaziyyat, statistika, mühəndislik"));
children.push(bullet("Texniki biliklər: Python (Pandas, NumPy); SQL (JOIN-lər, aggregasiya); Verilənlər bazası (PostgreSQL, MySQL); Linux əsasları"));
children.push(bullet("Üstünlük verilən biliklər: Spark, Airflow, dbt, cloud (AWS/GCP)"));
children.push(bullet("Şəxsi keyfiyyətlər: Detaylara diqqət, analitik düşüncə, problem həll etmə istəyi"));
children.push(h3("Data Analyst Namizədi:"));
children.push(bullet("Təhsil: Statistika, iqtisadiyyat, biznes informatikası, riyaziyyat"));
children.push(bullet("Texniki biliklər: SQL (intermediate); Excel / Google Sheets (advanced); Tableau, Power BI; Python (Pandas)"));
children.push(bullet("Üstünlük verilən biliklər: A/B test anlayışı, biznes metriklərini anlama"));
children.push(bullet("Şəxsi keyfiyyətlər: Data storytelling, kommunikasiya, təqdimat bacarığı"));
children.push(h2("3.3 AI & Backend Engineering Track"));
children.push(h3("Backend Developer (AI-Focused) Namizədi:"));
children.push(bullet("Təhsil: Kompüter elmləri, proqram mühəndisliyi, riyaziyyat"));
children.push(bullet("Texniki biliklər: Python (OOP) və ya Go/Node.js; REST API; Git (commit, branch, PR); Docker"));
children.push(bullet("Üstünlük verilən biliklər: FastAPI, LLM API-ları (OpenAI/Anthropic), Prompt Engineering"));
children.push(bullet("Şəxsi keyfiyyətlər: Mühəndis düşüncəsi, sistem dizaynına maraq, sürətlə öyrənmə"));
children.push(h2("3.4 Business & Delivery Track"));
children.push(h3("Business Analyst Namizədi:"));
children.push(bullet("Təhsil: Biznes, iqtisadiyyat, idarəetmə, informasiya sistemləri"));
children.push(bullet("Texniki biliklər: BPMN əsasları; Excel / data vizualizasiya; Jira, Confluence"));
children.push(bullet("Üstünlük verilən biliklər: SQL (əsas), Agile/Scrum anlayışı"));
children.push(bullet("Şəxsi keyfiyyətlər: Analitik düşüncə, yazılı ünsiyyət, stakeholder management"));
children.push(h3("IT Project Coordinator Namizədi:"));
children.push(bullet("Təhsil: Layihə idarəetməsi, biznes, texnologiya idarəetməsi"));
children.push(bullet("Texniki biliklər: Jira / Trello / Asana; Agile / Scrum; MS Project"));
children.push(bullet("Üstünlük verilən biliklər: PRINCE2 / PMP əsas anlayışları"));
children.push(bullet("Şəxsi keyfiyyətlər: Planlama, ünsiyyət, çoxşaxəli iş mühitini idarəetmə"));
children.push(pageBreak());

// ── SECTION 4 ─────────────────────────────────────────────────────────────────
children.push(h1("4. PROQRAM STRUKTURU (6-8 AY)"));
children.push(h2("4.1 Ümumi Fazalar"));
children.push(para("Proqram dörd əsas fazadan ibarətdir:"));
children.push(table2(
  ["Faz", "Müddət və Məzmun"],
  [
    ["FAZ 1 — Onboarding", "2 həftə: Şirkət mədəniyyəti, alətlər, komanda inteqrasiyası"],
    ["FAZ 2 — Strukturlaşdırılmış Təlim", "6-8 həftə: Texniki workshop-lar, kurslar, mini tapşırıqlar"],
    ["FAZ 3 — Real Layihə Fazası", "3-4 ay: Aktiv komandada iştirak, real problemlərin həlli"],
    ["FAZ 4 — Qiymətləndirmə & Graduation", "2-3 həftə: Final prezentasiya, 360° qiymətləndirmə, sertifikat"],
  ],
  [3800, 5838]
));
children.push(spacer(8));
children.push(h2("4.2 FAZ 1 — Onboarding (İlk 2 Həftə)"));
children.push(para("Məqsəd: İnternin şirkətin mədəniyyətinə, alətlərinə, komandaya inteqrasiyasını sürətlə təmin etmək."));
children.push(table2(
  ["Gün", "Fəaliyyət"],
  [
    ["1-2", "Şirkətin tarixi, missiyası, dəyərləri, komanda tanışlığı"],
    ["3-4", "İT alətlərinin qurulması (Git, Jira, Slack, Cloud access)"],
    ["5-7", "Şirkətin texniki arxitekturası, məhsul/xidmət ekosistemi ilə tanışlıq"],
    ["8-10", "Mentor təyinatı, fərdi inkişaf planı (IDP) hazırlanması"],
    ["11-14", "Mini-layihə tapşırığı (ilk texniki/analitik tapşırıq)"],
  ],
  [1800, 7838]
));
children.push(spacer(4));
children.push(para("Çıxış Meyarı: İntern mentoru, komandanı, əsas alətləri bilir və ilk mini-tapşırığı tamamlayır."));
children.push(h2("4.3 FAZ 2 — Strukturlaşdırılmış Təlim (6-8 Həftə)"));
children.push(para("Məqsəd: İxtisasa uyğun texniki və metodoloji biliklərin möhkəmləndirilməsi."));
children.push(bullet("Həftəlik 3-4 saat strukturlaşdırılmış öyrənmə sessiyası"));
children.push(bullet("Texniki workshop-lar (daxili senior mütəxəssislər tərəfindən)"));
children.push(bullet("Onlayn kurslarla kombinə (Udemy, Coursera, Pluralsight)"));
children.push(bullet("Həftəlik kiçik tapşırıqlar və kod/analiz reviewlar"));
children.push(h2("4.4 FAZ 3 — Real Layihə Fazası (3-4 Ay)"));
children.push(para("Məqsəd: İnternin real biznes problemlərinin həllinə cəlb edilməsi."));
children.push(h3("Prinsiplər:"));
children.push(bullet("Hər intern real komandaya (data, engineering, BA) inteqrasiya edilir"));
children.push(bullet("Sprint-lərə, standuplara, planlaşdırma sessiyalarına tam iştirak"));
children.push(bullet("Mentor nəzarəti altında müstəqil tapşırıqlar"));
children.push(bullet("Aylıq progress review (intern + mentor + HR)"));
children.push(h3("Mini-layihə Strukturu:"));
children.push(bullet("Həftə 1-2: Problemin anlaşılması, tələblərin toplanması"));
children.push(bullet("Həftə 3-6: Həll yolunun inkişafı (MVP)"));
children.push(bullet("Həftə 7-10: Test, iterasiya, təkmilləşdirmə"));
children.push(bullet("Həftə 11-12: Nəticənin komandaya təqdimatı"));
children.push(h2("4.5 FAZ 4 — Qiymətləndirmə & Graduation (Son 2-3 Həftə)"));
children.push(table2(
  ["Addım", "Fəaliyyət"],
  [
    ["Final Layihə Təqdimatı", "İntern 15-20 dəq ərzində liderlik heyətinə nəticələrini təqdim edir"],
    ["360° Qiymətləndirmə", "Mentor, komanda rəhbəri və HR-dan feedback"],
    ["Özünüqiymətləndirmə", "İnternin proqram haqqında refleksiya hesabatı"],
    ["Keçid Görüşməsi", "HR + Biznesdən keçid imkanlarının müzakirəsi"],
    ["Sertifikat", "Şirkət tərəfindən verilən tamamlama sertifikatı"],
  ],
  [3200, 6438]
));
children.push(pageBreak());

// ── SECTION 5 ─────────────────────────────────────────────────────────────────
children.push(h1("5. TƏLİM İZLƏRİ VƏ KURİKULUM"));
children.push(h2("5.1 DATA TRACK — Data Engineering & Analytics"));
children.push(h3("Modul 1: Əsaslar (Həftə 1-3)"));
children.push(table3(
  ["Mövzu", "Müddət", "Format"],
  [
    ["Python for Data (Pandas, NumPy)", "6 saat", "Workshop + Praktika"],
    ["SQL Intensive (advanced queries, window functions)", "8 saat", "Workshop + Tapşırıqlar"],
    ["Verilənlər bazası arxitekturası (OLTP vs OLAP)", "3 saat", "Mühazirə"],
    ["Git & CI/CD əsasları", "3 saat", "Praktiki sessiya"],
  ],
  [4600, 1600, 3438]
));
children.push(spacer(8));
children.push(h3("Modul 2a: Data Engineering (Həftə 4-6)"));
children.push(table3(
  ["Mövzu", "Müddət", "Format"],
  [
    ["ETL/ELT prosesləri", "6 saat", "Workshop"],
    ["Apache Airflow — pipeline avtomatlaşdırma", "8 saat", "Praktika"],
    ["dbt (Data Build Tool) — data transformasiya", "6 saat", "Praktika"],
    ["Cloud Data Warehouses (BigQuery / Snowflake)", "5 saat", "Lab"],
    ["Data quality & testing", "3 saat", "Mühazirə + Praktika"],
  ],
  [4600, 1600, 3438]
));
children.push(spacer(8));
children.push(h3("Modul 2b: Data Analytics (Həftə 4-6)"));
children.push(table3(
  ["Mövzu", "Müddət", "Format"],
  [
    ["Vizualizasiya alətləri (Power BI / Tableau)", "10 saat", "Praktika"],
    ["Statistik təhlil əsasları", "5 saat", "Workshop"],
    ["A/B Testing & Hipotez Yoxlaması", "5 saat", "Case Study"],
    ["Dashboard dizaynı & Storytelling", "4 saat", "Layihə"],
    ["Biznes metriklər & KPI qurmaq", "3 saat", "Mühazirə"],
  ],
  [4600, 1600, 3438]
));
children.push(spacer(8));
children.push(h2("5.2 AI & BACKEND ENGINEERING TRACK"));
children.push(h3("Modul 1: Backend Əsasları (Həftə 1-3)"));
children.push(table3(
  ["Mövzu", "Müddət", "Format"],
  [
    ["Python OOP & Clean Code", "6 saat", "Workshop"],
    ["REST API dizaynı (FastAPI)", "8 saat", "Praktika"],
    ["Verilənlər bazası inteqrasiyası (PostgreSQL + SQLAlchemy)", "6 saat", "Lab"],
    ["Docker & Konteynerləşmə", "5 saat", "Praktika"],
    ["Git workflow (branching strategy, PR review)", "3 saat", "Sessiya"],
  ],
  [4600, 1600, 3438]
));
children.push(spacer(8));
children.push(h3("Modul 2: AI İnteqrasiyası (Həftə 4-6)"));
children.push(table3(
  ["Mövzu", "Müddət", "Format"],
  [
    ["LLM əsasları & Prompt Engineering", "5 saat", "Workshop"],
    ["OpenAI / Anthropic Claude API inteqrasiyası", "6 saat", "Praktika"],
    ["RAG (Retrieval-Augmented Generation) arxitekturası", "5 saat", "Lab"],
    ["AI-powered API xidmətləri qurmaq", "8 saat", "Mini-layihə"],
    ["AI etikası, məhdudiyyətlər, təhlükəsizlik", "3 saat", "Mühazirə"],
  ],
  [4600, 1600, 3438]
));
children.push(spacer(8));
children.push(h2("5.3 BUSINESS & DELIVERY TRACK"));
children.push(h3("Modul 1: BA Əsasları (Həftə 1-3)"));
children.push(table3(
  ["Mövzu", "Müddət", "Format"],
  [
    ["Biznes tələblərinin toplanması (interview, workshop)", "5 saat", "Role-play + Praktika"],
    ["Proseslərin modelləşdirilməsi (BPMN)", "5 saat", "Workshop"],
    ["Use Case & User Story yazma", "5 saat", "Praktika"],
    ["Jira & Confluence idarəetməsi", "4 saat", "Praktika"],
    ["Maraqlı tərəflərlə ünsiyyət (Stakeholder Management)", "3 saat", "Mühazirə + Simulasiya"],
  ],
  [4600, 1600, 3438]
));
children.push(spacer(8));
children.push(h3("Modul 2: Agile & Layihə Koordinasiyası (Həftə 4-6)"));
children.push(table3(
  ["Mövzu", "Müddət", "Format"],
  [
    ["Agile / Scrum metodologiyası", "6 saat", "Workshop"],
    ["Sprint planlaması, retrospektiv, standup", "5 saat", "Real komandaya qatılma"],
    ["Risk idarəetməsi əsasları", "4 saat", "Case Study"],
    ["Hesabat hazırlama & təqdimat", "4 saat", "Praktika"],
    ["AI alətlərinin BA proseslərinə tətbiqi", "3 saat", "Workshop"],
  ],
  [4600, 1600, 3438]
));
children.push(pageBreak());

// ── SECTION 6 ─────────────────────────────────────────────────────────────────
children.push(h1("6. MENTORLUQ VƏ NƏZARƏT MODELİ"));
children.push(h2("6.1 Mentor Rolu və Seçim Meyarları"));
children.push(h3("Kimlər mentor ola bilər:"));
children.push(bullet("Minimum 3 il şirkətdaxili iş təcrübəsi olan mütəxəssislər"));
children.push(bullet("Yüksək texniki / funksional peşəkarlıq"));
children.push(bullet("Öyrətmək istəyi (könüllülük prinsipi)"));
children.push(bullet("HR tərəfindən keçirilən qısa mentor hazırlıq sessiyasından keçiblər"));
children.push(spacer(4));
children.push(new Paragraph({
  spacing: { before: 80, after: 80 },
  children: [new TextRun({ text: "Mentor Yükü: 1 mentor → maksimum 2 intern", font: "Calibri", size: 22, bold: true })],
}));
children.push(h3("Mentorların Əsas Vəzifələri:"));
children.push(bullet("Həftəlik 1:1 görüş (45-60 dəq)"));
children.push(bullet("Texniki sualları cavablandırmaq"));
children.push(bullet("Kod / analiz review"));
children.push(bullet("Aylıq progress hesabatı doldurmaq"));
children.push(bullet("Xarici maneələri HR / rəhbərliyə çatdırmaq"));
children.push(h2("6.2 Checkpoint Strukturu"));
children.push(table4(
  ["Checkpoint", "Tezlik", "İştirakçılar", "Formatı"],
  [
    ["Həftəlik 1:1", "Həftəlik", "Intern + Mentor", "Qısa görüş (45 dəq)"],
    ["Aylıq Progress Review", "Aylıq", "Intern + Mentor + HR", "Strukturlaşdırılmış görüş"],
    ["Mid-Program Review", "Proqramın yarısında", "Intern + Mentor + Komanda Rəhbəri", "Rəsmi qiymətləndirmə"],
    ["Final Evaluation", "Proqramın sonunda", "Intern + Mentor + HR + Biznesdən təmsilçi", "Final prezentasiya"],
  ],
  [2400, 1800, 2800, 2638]
));
children.push(spacer(8));
children.push(h2("6.3 Mentorların Motivasiyası"));
children.push(bullet("Tanınma: \"Mentor of the Quarter\" mükafatı"));
children.push(bullet("Performans qeydiyyatı: Mentorluq fəaliyyəti performans KPI-larına daxil edilir"));
children.push(bullet("Peşəkar inkişaf: Mentorluq liderlik yolunun bir hissəsi kimi qəbul edilir"));
children.push(pageBreak());

// ── SECTION 7 ─────────────────────────────────────────────────────────────────
children.push(h1("7. İŞ MODELİ"));
children.push(h2("7.1 Ödənişli vs Ödənişsiz Staj"));
children.push(table3(
  ["Meyar", "Ödənişli Staj", "Ödənişsiz Staj"],
  [
    ["Namizəd Keyfiyyəti", "Daha yüksək (rəqabət artır)", "Aşağı (yalnız motivasiyalı namizədlər)"],
    ["Şirkətin Öhdəliyi", "Daha yüksək (formal əmək münasibəti)", "Daha az"],
    ["Hüquqi Risklər", "Minimal (qanunvericiliyə uyğun)", "Bəzi ölkələrdə riskli ola bilər"],
    ["Employer Brand", "Güclü (cəlbedici)", "Zəif"],
    ["Performans Motivasiyası", "Yüksək", "Orta"],
    ["Şirkətin Xərci", "Mövcud (amma gətirim böyükdür)", "Minimal"],
  ],
  [3000, 3319, 3319]
));
children.push(spacer(8));
children.push(new Paragraph({
  spacing: { before: 100, after: 100 },
  shading: { fill: "FFF2CC", type: ShadingType.CLEAR },
  children: [new TextRun({
    text: "Tövsiyə — Hibrid model: Proqramın 1-ci ayı ödənişsiz (sınaq dövrü). 2-ci aydan etibarən performansa əsaslanan ödəniş (stajçı maaş əmsalı — region bazarının 40-60%-i).",
    font: "Calibri", size: 22, bold: true,
  })],
}));
children.push(spacer(4));
children.push(h3("Tövsiyə olunan Ödəniş Strukturu (Azərbaycan bazarı):"));
children.push(table2(
  ["Track", "Aylıq Staj Ödənişi (AZN)"],
  [
    ["Data Engineering", "600 – 900"],
    ["Data Analytics", "500 – 800"],
    ["AI & Backend", "700 – 1,000"],
    ["Business Analyst", "500 – 700"],
    ["IT Project Coordinator", "450 – 650"],
  ],
  [4819, 4819]
));
children.push(spacer(8));
children.push(h2("7.2 İş Modeli — Struktur Hibrid Model"));
children.push(table3(
  ["Faz", "Ofis Tələbi", "İzah"],
  [
    ["Onboarding (Faz 1)", "5 gün / həftə", "Ofisdə şirkət mədəniyyətinə inteqrasiya vacibdir"],
    ["Təlim Fazası (Faz 2)", "3 gün / həftə", "Workshop-lar üçün fiziki iştirak; qalan günlər uzaqdan"],
    ["Layihə Fazası (Faz 3)", "2-3 gün / həftə", "Komanda ilə sinxronizasiya + çevik iş"],
    ["Final Faz (Faz 4)", "5 gün / həftə", "Prezentasiya hazırlığı üçün tam iştirak"],
  ],
  [2800, 1900, 4938]
));
children.push(pageBreak());

// ── SECTION 8 ─────────────────────────────────────────────────────────────────
children.push(h1("8. QİYMƏTLƏNDİRMƏ VƏ KPI ÇƏRÇİVƏSİ"));
children.push(h2("8.1 Performans Metriklər (İntern üçün)"));
children.push(h3("Texniki / Funksional Göstəricilər (60%):"));
children.push(table3(
  ["Meyar", "Çəki", "Qiymətləndirən"],
  [
    ["Texniki tapşırıqların keyfiyyəti", "25%", "Mentor"],
    ["Layihəyə töhfənin əhəmiyyəti", "20%", "Komanda Rəhbəri"],
    ["Öyrənmə sürəti (skill gap azalması)", "15%", "Mentor + HR"],
  ],
  [4638, 1500, 3500]
));
children.push(spacer(8));
children.push(h3("Davranış / Soft Skills (40%):"));
children.push(table3(
  ["Meyar", "Çəki", "Qiymətləndirən"],
  [
    ["Proaktivlik və müstəqillik", "15%", "Mentor"],
    ["Komanda işi və ünsiyyət", "15%", "Komanda"],
    ["Vaxt idarəetməsi, öhdəliklərə sadiqlik", "10%", "Mentor + HR"],
  ],
  [4638, 1500, 3500]
));
children.push(spacer(8));
children.push(h2("8.2 Graduation Meyarları"));
children.push(bullet("Orta qiymət >= 3.5 / 5.0 (bütün meyarlar üzrə)"));
children.push(bullet("Final layihəsini uğurla təqdim etmək"));
children.push(bullet("Proqramın >= 85%-ni tamamlamaq (icazəsiz qayıb yoxdur)"));
children.push(bullet("360° feedback-də \"inkişaf əyrisinin yuxarı olması\" qeydi"));
children.push(h2("8.3 Full-Time Keçid Meyarları"));
children.push(table3(
  ["Səviyyə", "Qiymət Aralığı", "Qərar"],
  [
    ["Yüksək Performans", "4.5 – 5.0", "Prioritet təklif + yüksək maaş başlanğıcı"],
    ["Yaxşı Performans", "3.5 – 4.4", "Standart iş təklifi"],
    ["Orta Performans", "2.5 – 3.4", "Uzadılmış probation dövrü ilə şərtli təklif"],
    ["Aşağı Performans", "< 2.5", "Full-time təklif yoxdur, sertifikat verilir"],
  ],
  [3000, 2000, 4638]
));
children.push(spacer(8));
children.push(h2("8.4 Proqram Səviyyəsində KPI-lar (Şirkət üçün)"));
children.push(table3(
  ["KPI", "Hədəf", "Tezlik"],
  [
    ["Proqramu tamamlayan intern faizi", ">= 85%", "Hər proqram dövrü"],
    ["Full-time keçid faizi", ">= 60%", "İllik"],
    ["Mentor məmnuniyyət skoru", ">= 4.2 / 5.0", "Yarımillik"],
    ["İntern NPS (tövsiyəetmə skoru)", ">= 50", "Hər proqram sonunda"],
    ["Proqram ROI", ">= 200%", "İllik"],
    ["Xarici senior işə qəbuldan azalma", "30-40%", "İllik"],
  ],
  [4238, 2000, 3400]
));
children.push(pageBreak());

// ── SECTION 9 ─────────────────────────────────────────────────────────────────
children.push(h1("9. ALƏTLƏR VƏ MÜHİT"));
children.push(h2("9.1 Bütün Tracklər üçün Ümumi Alətlər"));
children.push(table3(
  ["Kateqoriya", "Alət", "Məqsəd"],
  [
    ["Versiya Nəzarəti", "Git + GitHub / GitLab", "Kod idarəetməsi"],
    ["Layihə İdarəetməsi", "Jira / Linear", "Sprint, tapşırıq, backlog"],
    ["Bilik Bazası", "Confluence / Notion", "Sənədləşmə, wiki"],
    ["Ünsiyyət", "Slack / Microsoft Teams", "Komanda ünsiyyəti"],
    ["Video Görüşlər", "Zoom / Google Meet", "Uzaqdan sessiyalar"],
    ["Təlim Platforması", "Udemy for Business / Coursera", "Özünüidarəli öyrənmə"],
  ],
  [2800, 3400, 3438]
));
children.push(spacer(8));
children.push(h2("9.2 Data Track üçün Alətlər"));
children.push(table2(
  ["Kateqoriya", "Alət"],
  [
    ["Proqramlaşdırma", "Python (Pandas, NumPy, SQLAlchemy)"],
    ["Verilənlər bazası", "PostgreSQL, BigQuery / Snowflake"],
    ["ETL / Orchestration", "Apache Airflow, dbt"],
    ["Vizualizasiya", "Power BI, Tableau, Looker, Metabase"],
    ["Notebook", "Jupyter, Google Colab"],
    ["Cloud", "AWS S3 / GCS (sandbox environment)"],
  ],
  [3200, 6438]
));
children.push(spacer(8));
children.push(h2("9.3 AI & Backend Track üçün Alətlər"));
children.push(table2(
  ["Kateqoriya", "Alət"],
  [
    ["Proqramlaşdırma", "Python (FastAPI), Go (opsional)"],
    ["AI / LLM", "OpenAI API, Anthropic Claude API, LangChain"],
    ["Konteynerləşmə", "Docker, docker-compose"],
    ["Verilənlər bazası", "PostgreSQL, Redis"],
    ["Testing", "Pytest, Postman"],
    ["Monitoring", "Grafana, Prometheus"],
    ["AI Köməkçilər", "GitHub Copilot, Cursor AI"],
  ],
  [3200, 6438]
));
children.push(spacer(8));
children.push(h2("9.4 BA / Koordinasiya Track üçün Alətlər"));
children.push(table2(
  ["Kateqoriya", "Alət"],
  [
    ["Proses Modelləşdirmə", "Lucidchart, draw.io (BPMN)"],
    ["Layihə Planlaması", "Jira, Trello, MS Project"],
    ["Sənədləşmə", "Confluence, Google Docs"],
    ["Prezentasiya", "PowerPoint, Google Slides"],
    ["Analiz", "Excel (advanced), Google Sheets"],
    ["AI Köməkçilər", "ChatGPT / Claude (BA sənədlər üçün)"],
  ],
  [3200, 6438]
));
children.push(pageBreak());

// ── SECTION 10 ────────────────────────────────────────────────────────────────
children.push(h1("10. RİSKLƏR VƏ MİTİQASİYA"));
children.push(h2("10.1 Əsas Risklər"));
children.push(table4(
  ["Risk", "Ehtimal", "Təsir", "Prioritet"],
  [
    ["Yüksək dropout (proqramı tərk etmə)", "Orta", "Yüksək", "Kritik"],
    ["Aşağı engagement (passivlik)", "Orta", "Yüksək", "Kritik"],
    ["Bacarıq uyğunsuzluğu (skill mismatch)", "Aşağı-Orta", "Orta", "Əhəmiyyətli"],
    ["Mentor yükü (overload)", "Orta", "Orta", "Əhəmiyyətli"],
    ["İnternin rəqibə keçməsi", "Aşağı", "Yüksək", "Nəzarət altında"],
    ["Proqram sənədləşməsinin zəifliyi", "Yüksək", "Orta", "Əhəmiyyətli"],
  ],
  [3600, 1600, 1600, 2838]
));
children.push(spacer(8));
children.push(h2("10.2 Mitirasiya Strategiyaları"));
children.push(h3("Risk 1 — Yüksək Dropout"));
children.push(bullet("Seçim mərhələsində motivasiyanı dərindən qiymətləndirmək"));
children.push(bullet("Ödənişli staj modeli (Faz 2-dən etibarən)"));
children.push(bullet("Aylıq 1:1 HR görüşləri ilə erkən siqnal aşkarlaması"));
children.push(bullet("Şəffaf proqram gözləntiləri (ilk gündən yazılı olaraq)"));
children.push(h3("Risk 2 — Aşağı Engagement"));
children.push(bullet("Onboarding-dən etibarən real layihəyə minimal töhfə"));
children.push(bullet("Şirkət daxilindəki all-hands görüşlərə intern iştirakı"));
children.push(bullet("Gamification: badges, sertifikatlar, milestone qeydiyyatı"));
children.push(bullet("Ayda bir dəfə intern \"demo day\""));
children.push(h3("Risk 3 — Bacarıq Uyğunsuzluğu"));
children.push(bullet("Seçim zamanı texniki test / case study"));
children.push(bullet("30 günlük sınaq dövrü sonunda \"continue/stop\" qərarı mexanizmi"));
children.push(bullet("Track dəyişdirmə imkanı"));
children.push(h3("Risk 4 — Mentor Overload"));
children.push(bullet("1 mentor → maksimum 2 intern qaydası"));
children.push(bullet("Mentorların iş yükünün rəsmi olaraq planlanmasına daxil edilməsi"));
children.push(bullet("Mentorluq üçün azaldılmış layihə öhdəlikləri"));
children.push(h3("Risk 5 — İnternin Rəqibə Keçməsi"));
children.push(bullet("Yüksək performanslılara erkən full-time təklif"));
children.push(bullet("Non-compete clause (yerli qanunvericiliyə uyğun)"));
children.push(bullet("Güclü mədəniyyət və bağlılıq hissi yaratmaq"));
children.push(pageBreak());

// ── SECTION 11 ────────────────────────────────────────────────────────────────
children.push(h1("11. GÖZLƏNİLƏN BİZNES TƏSİRİ"));
children.push(h2("11.1 Talent Pipeline Yaratmaq"));
children.push(para("İllik 15-25 intern → Mezun olandan 60% full-time → 9-15 yeni mütəxəssis / il. Bu, xarici bazardan alınmış eyni sayda mütəxəssisin xərclərinin 40-60% aşağı olması deməkdir — çünki daxili yetişdirilmiş kadr artıq şirkətin sistemlərini bilir, onboarding xərci minimaldır, mədəni uyum yüksəkdir, loyallıq daha güclüdür."));
children.push(h2("11.2 Maliyyə Effektivliyi"));
children.push(table3(
  ["Göstərici", "Xarici Senior İşə Qəbul", "Daxili İntern → Junior"],
  [
    ["Recruitment xərci (orta)", "3,000-8,000 AZN", "500-1,000 AZN"],
    ["Onboarding müddəti", "2-3 ay", "Proqram daxilindədir"],
    ["Başlanğıc maaş", "Bazar qiymətinin 100%", "Bazar qiymətinin 60-75%"],
    ["Şirkətə uyum riski", "Yüksək", "Aşağı"],
    ["1 il sonra retention", "65-70%", "80-90%"],
  ],
  [3400, 3119, 3119]
));
children.push(spacer(8));
children.push(h3("Proqramın Təxmini İllik Xərcləri (15 intern üçün):"));
// Build this table manually so last row can be bold
{
  const ws = [5200, 4438];
  const totalW = ws[0] + ws[1];
  const border = { style: BorderStyle.SINGLE, size: 4, color: "C0C8D8" };
  const borders = { top: border, bottom: border, left: border, right: border };

  function costCell(text, isHdr, altRow, w, isBold) {
    return new TableCell({
      width: { size: w, type: WidthType.DXA },
      borders,
      shading: { fill: isHdr ? NAVY : altRow ? LIGHT_BLUE : WHITE, type: ShadingType.CLEAR },
      margins: CELL_MARGINS,
      verticalAlign: VerticalAlign.CENTER,
      children: [new Paragraph({
        spacing: { before: 20, after: 20 },
        children: [new TextRun({ text, font: "Calibri", size: 20, bold: isBold || isHdr, color: isHdr ? WHITE : "000000" })],
      })],
    });
  }

  const costTable = new Table({
    width: { size: totalW, type: WidthType.DXA },
    columnWidths: ws,
    rows: [
      new TableRow({ tableHeader: true, children: [
        costCell("Xərc Maddəsi", true, false, ws[0]),
        costCell("Təxmini Məbləğ (AZN/il)", true, false, ws[1]),
      ]}),
      new TableRow({ children: [costCell("İntern ödənişləri (Faz 2-dən)", false, false, ws[0]), costCell("60,000 – 90,000", false, false, ws[1])] }),
      new TableRow({ children: [costCell("Mentor vaxtı (opportunity cost)", false, true, ws[0]), costCell("15,000 – 25,000", false, true, ws[1])] }),
      new TableRow({ children: [costCell("Təlim materialları / platformalar", false, false, ws[0]), costCell("5,000 – 10,000", false, false, ws[1])] }),
      new TableRow({ children: [costCell("İnzibati xərclər", false, true, ws[0]), costCell("3,000 – 5,000", false, true, ws[1])] }),
      new TableRow({ children: [costCell("Cəmi", false, false, ws[0], true), costCell("83,000 – 130,000", false, false, ws[1], true)] }),
    ],
  });
  children.push(costTable);
}
children.push(spacer(8));
children.push(h2("11.3 İnnovasiya və AI Adaptasiyasının Sürətləndirilməsi"));
children.push(bullet("Gənc internlər ən son AI alətlərini öyrənərək mövcud komandaları stimullaşdırır"));
children.push(bullet("AI-first yanaşma yeni nəsildən şirkətin bütün komandalarına yayılır"));
children.push(bullet("İnternlər tez-tez \"gözlənilməz suallar\" verərək köhnəlmiş prosesləri aşkar edir"));
children.push(pageBreak());

// ── SECTION 12 ────────────────────────────────────────────────────────────────
children.push(h1("12. İMPLEMENTASİYA YOLU XƏRİTƏSİ"));
children.push(h2("12.1 Pilot Proqram Planı (İl 1)"));
children.push(h3("AY 1-2: Hazırlıq Mərhələsi"));
children.push(bullet("Proqram komandası (HR + CTO + PM) formalaşdırılır"));
children.push(bullet("Mentor seçimi və təlimatlandırılması"));
children.push(bullet("Kurikulum və qiymətləndirmə alətlərinin hazırlanması"));
children.push(bullet("Hüquqi çərçivə (müqavilə şablonları, ödəniş strukturu)"));
children.push(bullet("Universitetlər / platformalarla əlaqə qurulur"));
children.push(h3("AY 3: İşə Qəbul"));
children.push(bullet("Vakansiyaların elan edilməsi (LinkedIn, universitetlər, ASOIU, BDU, ADA)"));
children.push(bullet("CV review → Texniki test → Müsahibə"));
children.push(bullet("15-25 intern seçilir (3 track üzrə)"));
children.push(h3("AY 4: Proqramın Başlanması"));
children.push(bullet("Onboarding (Faz 1) — 2 həftə"));
children.push(bullet("Strukturlaşdırılmış Təlim (Faz 2) — 6-8 həftə"));
children.push(bullet("Real Layihə Fazasına Keçid (Faz 3)"));
children.push(h3("AY 4-10: Layihə Fazası"));
children.push(bullet("Aylıq checkpoint-lər"));
children.push(bullet("Mid-program review (Ay 6-da)"));
children.push(bullet("Davamlı mentor dəstəyi"));
children.push(h3("AY 10-11: Qiymətləndirmə & Graduation"));
children.push(bullet("Final layihə prezentasiyaları"));
children.push(bullet("360° qiymətləndirmə"));
children.push(bullet("Full-time keçid qərarları"));
children.push(h3("AY 12: Retrospektiv & Növbəti Dövrün Planlanması"));
children.push(bullet("Proqram KPI-larının icmalı"));
children.push(bullet("Dərs alınan məqamların sənədləşdirilməsi"));
children.push(bullet("2-ci ilin planı (genişləndirilmiş cohort)"));
children.push(h2("12.2 Genişlənmə Yol Xəritəsi"));
children.push(table2(
  ["Dövr", "Fəaliyyət"],
  [
    ["İl 1 (Pilot)", "15-25 intern, 3 track, 1 cohort"],
    ["İl 2 (Böyümə)", "30-40 intern, əlavə track-lər (DevOps, QA), 2 cohort/il"],
    ["İl 3 (Miqyaslanma)", "Universitetlərlə rəsmi tərəfdaşlıq, dövlət dəstəyi proqramları ilə sinerjiya"],
    ["İl 4+", "Şirkətin \"Technology Academy\" brendinin qurulması"],
  ],
  [2400, 7238]
));
children.push(spacer(8));
children.push(h2("12.3 Cavabdehlik Matrisi (RACI)"));
children.push(table6(
  ["Fəaliyyət", "CTO", "HR Director", "Program Manager", "Mentor", "İntern"],
  [
    ["Proqram strategiyası", "R/A", "C", "C", "I", "I"],
    ["Namizəd seçimi", "C", "R/A", "R", "C", "—"],
    ["Kurikulum hazırlığı", "A", "C", "R", "C", "I"],
    ["Günlük mentorluq", "I", "I", "C", "R/A", "C"],
    ["Aylıq qiymətləndirmə", "C", "R", "A", "R", "R"],
    ["Full-time qərar", "A", "R", "C", "C", "—"],
    ["Proqram KPI hesabatı", "I", "C", "R/A", "I", "I"],
  ],
  [2800, 1000, 1300, 1600, 1200, 1738]
));
children.push(spacer(4));
children.push(para("Qeyd: R = Responsible, A = Accountable, C = Consulted, I = Informed"));
children.push(pageBreak());

// ── CONCLUSION ────────────────────────────────────────────────────────────────
children.push(h1("YEKUN"));
children.push(para("Bu Staj İnkişaf Proqramı şirkətimizin texnoloji gələcəyinə edilən strateji investisiyadır. Düzgün icra edildiyi halda:"));
children.push(bullet("Şirkət xarici işə qəbuldan asılılığını azaldacaq"));
children.push(bullet("Özünün yetişdirdiyi, mədəniyyətini, sistemlərini dərindən bilən mütəxəssislər hovuzu yaradacaq"));
children.push(bullet("AI və data texnologiyalarının şirkət daxilindəki yayılmasını sürətləndirəcək"));
children.push(bullet("Employer brand olaraq gənclər arasında tanınan, seçilən bir şirkətə çevriləcək"));
children.push(spacer(20));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 200, after: 80 },
  children: [new TextRun({ text: '"The best talent is not found — it is built."', font: "Calibri", size: 22, italics: true })],
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before: 40, after: 200 },
  children: [new TextRun({ text: '("Ən yaxşı kadr tapılmır — yetişdirilir.")', font: "Calibri", size: 22, italics: true })],
}));

// ─── DOCUMENT ASSEMBLY ────────────────────────────────────────────────────────
const doc = new Document({
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{
          level: 0,
          format: LevelFormat.BULLET,
          text: "\u2022",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
    ],
  },
  styles: {
    default: {
      document: { run: { font: "Calibri", size: 22 } },
    },
    paragraphStyles: [
      {
        id: "Heading1",
        name: "Heading 1",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { font: "Calibri", size: 28, bold: true, color: NAVY },
        paragraph: { spacing: { before: 280, after: 140 }, outlineLevel: 0 },
      },
      {
        id: "Heading2",
        name: "Heading 2",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { font: "Calibri", size: 24, bold: true, color: DARK_BLUE },
        paragraph: { spacing: { before: 220, after: 110 }, outlineLevel: 1 },
      },
      {
        id: "Heading3",
        name: "Heading 3",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { font: "Calibri", size: 22, bold: true },
        paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 2 },
      },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: PAGE_W, height: PAGE_H },
        margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN },
      },
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 80, after: 80 },
          children: [
            new TextRun({ text: "HR Strategiya Departamenti | CTO Ofisi | Proqram İdarəetmə Komandası | Aprel 2026    ", font: "Calibri", size: 18, color: GRAY_TEXT }),
            new TextRun({ children: [PageNumber.CURRENT], font: "Calibri", size: 18, color: GRAY_TEXT }),
          ],
        })],
      }),
    },
    children,
  }],
});

const outPath = path.join(__dirname, "Staj_Proqrami_Nizamnamesi.docx");
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(outPath, buf);
  console.log("SUCCESS:", outPath);
  console.log("File size:", fs.statSync(outPath).size, "bytes");
}).catch(err => {
  console.error("ERROR:", err);
  process.exit(1);
});
