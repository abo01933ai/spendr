#!/usr/bin/env node
/**
 * parse-finance.js
 * 解析 ~/Obsidian/Finance/YYYY-MM.md → data/finance-data.json
 */

const fs = require('fs');
const path = require('path');
const os = require('os');

const FINANCE_DIR = path.join(os.homedir(), 'Obsidian', 'Finance');
const OUTPUT_FILE = path.join(__dirname, '..', 'data', 'finance-data.json');

// 類別顏色對應
const CATEGORY_COLORS = {
  '餐點': '#FF6B6B',
  '飲料': '#4ECDC4',
  '日常消費': '#45B7D1',
  '固定支出': '#96CEB4',
  '旅遊': '#FFEAA7',
  '娛樂': '#DDA0DD',
  '學習投資': '#98D8C8',
  '服飾': '#F7DC6F',
  '交通': '#AED6F1',
  '醫療': '#F1948A',
  '寵物': '#A9CCE3',
  '捐款': '#A8E6CF',
  '用品': '#FFD3B6',
  '紅包': '#FF8B94',
  '工具': '#C3B1E1',
  '玩具': '#FFDAC1',
  '伴手禮': '#E2B0FF',
  '其他': '#B2BEB5',
};

function parseAmount(str) {
  if (!str) return 0;
  // 移除 NT$、逗號、空白，取負數
  const cleaned = str.replace(/NT\$|,|\s/g, '').trim();
  const num = parseFloat(cleaned);
  return isNaN(num) ? 0 : num;
}

function parseMonthFile(filePath) {
  const content = fs.readFileSync(filePath, 'utf-8');
  const lines = content.split('\n');
  
  const records = [];
  let currentDate = null;
  const fileName = path.basename(filePath, '.md'); // e.g. 2026-03
  const [year, month] = fileName.split('-');
  
  let stopParsing = false;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    
    // 遇到本月累積/統計區塊就停止
    if (/本月累積|本月統計|固定支出對照|固定支出合計/.test(line)) {
      stopParsing = true;
    }
    if (stopParsing) continue;
    
    // 偵測日期標題：## 03-01 or ## 03-01（四）or ### 04-01（四）
    const dateMatch = line.match(/^#{2,3}\s+(\d{2})-(\d{2})/);
    if (dateMatch) {
      currentDate = `${year}-${month}-${dateMatch[2]}`;
      continue;
    }
    
    // 舊格式：## MM-DD
    const oldDateMatch = line.match(/^#{2,3}\s+(\d{2})\/(\d{2})/);
    if (oldDateMatch) {
      currentDate = `${year}-${month}-${oldDateMatch[2]}`;
      continue;
    }
    
    if (!currentDate) continue;
    
    // 解析表格行（跳過標題、分隔、合計行）
    if (!line.startsWith('|')) continue;
    if (line.includes('---')) continue;
    if (line.includes('類型') || line.includes('項目') || line.includes('分類')) continue;
    if (line.includes('當日合計') || line.includes('小計') || line.includes('固定支出小計')) continue;
    if (line.includes('本月合計') || line.includes('本月累積') || line.includes('月統計') || line.includes('固定支出合計')) continue;
    if (line.includes('**')) continue; // 粗體行（小計/合計）
    
    const cols = line.split('|').map(c => c.trim()).filter(c => c !== '');
    if (cols.length < 2) continue;
    
    // 支援兩種格式：
    // 舊: | 類型 | 項目 | 金額 |
    // 新: | 項目 | 金額 | 分類 | 備註 |
    let category, item, amountStr;
    
    if (cols.length >= 3) {
      const possibleAmount1 = cols[2]; // 舊格式金額位置
      const possibleAmount2 = cols[1]; // 新格式金額位置
      
      const isOldFormat = possibleAmount1 && (possibleAmount1.includes('-') || possibleAmount1.includes('NT$'));
      const isNewFormat = possibleAmount2 && (possibleAmount2.includes('-') || possibleAmount2.includes('NT$'));
      
      if (isOldFormat) {
        // 舊格式: 類型 | 項目 | 金額
        category = cols[0];
        item = cols[1];
        amountStr = cols[2];
      } else if (isNewFormat && cols.length >= 3) {
        // 新格式: 項目 | 金額 | 分類
        item = cols[0];
        amountStr = cols[1];
        category = cols[2];
      } else {
        continue;
      }
    } else if (cols.length === 2) {
      item = cols[0];
      amountStr = cols[1];
      category = '其他';
    } else {
      continue;
    }
    
    const amount = parseAmount(amountStr);
    if (amount === 0) continue;
    
    records.push({
      date: currentDate,
      category: category || '其他',
      item: item || '',
      amount: amount,
    });
  }
  
  return records;
}

function buildDashboardData(allRecords) {
  // 按月分組
  const byMonth = {};
  allRecords.forEach(r => {
    const mon = r.date.slice(0, 7);
    if (!byMonth[mon]) byMonth[mon] = [];
    byMonth[mon].push(r);
  });
  
  const months = Object.keys(byMonth).sort();
  
  const monthlyData = months.map(mon => {
    const records = byMonth[mon];
    
    // 按類別加總
    const byCategory = {};
    records.forEach(r => {
      if (!byCategory[r.category]) byCategory[r.category] = 0;
      byCategory[r.category] += r.amount;
    });
    
    // 按日期加總
    const byDate = {};
    records.forEach(r => {
      if (!byDate[r.date]) byDate[r.date] = 0;
      byDate[r.date] += r.amount;
    });
    
    const total = records.reduce((s, r) => s + r.amount, 0);
    
    return {
      month: mon,
      total: Math.round(total),
      byCategory: Object.entries(byCategory)
        .map(([cat, amt]) => ({
          category: cat,
          amount: Math.round(amt),
          color: CATEGORY_COLORS[cat] || CATEGORY_COLORS['其他'],
        }))
        .sort((a, b) => a.amount - b.amount),
      byDate: Object.entries(byDate)
        .map(([date, amt]) => ({ date, amount: Math.round(amt) }))
        .sort((a, b) => a.date.localeCompare(b.date)),
      records: records.sort((a, b) => a.date.localeCompare(b.date)),
    };
  });
  
  return {
    generated: new Date().toISOString(),
    months: monthlyData,
    categoryColors: CATEGORY_COLORS,
  };
}

// Main
const mdFiles = fs.readdirSync(FINANCE_DIR)
  .filter(f => /^\d{4}-\d{2}\.md$/.test(f))
  .map(f => path.join(FINANCE_DIR, f));

if (mdFiles.length === 0) {
  console.error('找不到任何記帳檔案');
  process.exit(1);
}

let allRecords = [];
mdFiles.forEach(f => {
  try {
    const records = parseMonthFile(f);
    allRecords = allRecords.concat(records);
    console.log(`✓ ${path.basename(f)}: ${records.length} 筆`);
  } catch (e) {
    console.warn(`⚠ 解析失敗 ${path.basename(f)}: ${e.message}`);
  }
});

const data = buildDashboardData(allRecords);

fs.mkdirSync(path.dirname(OUTPUT_FILE), { recursive: true });
fs.writeFileSync(OUTPUT_FILE, JSON.stringify(data, null, 2));
console.log(`\n✅ 輸出至 ${OUTPUT_FILE}`);
console.log(`   ${data.months.length} 個月份，${allRecords.length} 筆記錄`);
