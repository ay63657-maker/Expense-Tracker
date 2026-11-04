function toggleMenu() {
  const nav = document.getElementById("navLinks");
  if (nav) nav.classList.toggle("open");
}

document.addEventListener("DOMContentLoaded", () => {
  // Close mobile nav when clicking outside
  document.addEventListener("click", (e) => {
    const nav = document.getElementById("navLinks");
    const btn = document.querySelector(".menu-btn");
    if (nav && nav.classList.contains("open")) {
      if (!nav.contains(e.target) && (!btn || !btn.contains(e.target))) {
        nav.classList.remove("open");
      }
    }
  });

  const canvas = document.getElementById("monthlyChart");
  if (!canvas || !window.reportData) return;

  function renderChart() {
    const data = window.reportData;
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth || (canvas.parentElement ? canvas.parentElement.clientWidth : 600);
    const height = 260;

    canvas.width = width * ratio;
    canvas.height = height * ratio;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(ratio, ratio);

    if (!data.months || data.months.length === 0) {
      ctx.fillStyle = "#94a3b8";
      ctx.font = "14px Arial";
      ctx.textAlign = "center";
      ctx.fillText("No monthly transaction data available yet.", width / 2, height / 2);
      return;
    }

    const incomeVals = Array.isArray(data.income) ? data.income : [];
    const expenseVals = Array.isArray(data.expense) ? data.expense : [];
    const maxVal = Math.max(1, ...incomeVals, ...expenseVals);

    const left = 60, right = 20, top = 25, bottom = 35;
    const chartW = width - left - right;
    const chartH = height - top - bottom;

    ctx.font = "11px Arial";
    ctx.textAlign = "right";
    ctx.fillStyle = "#64748b";
    ctx.strokeStyle = "#e2e8f0";

    for (let i = 0; i <= 4; i++) {
      const y = top + (chartH * i / 4);
      ctx.beginPath();
      ctx.moveTo(left, y);
      ctx.lineTo(width - right, y);
      ctx.stroke();
      ctx.fillText("₹" + Math.round(maxVal * (1 - i / 4)).toLocaleString(), left - 8, y + 4);
    }

    const count = Math.max(data.months.length, 1);
    const group = chartW / count;
    const bar = Math.min(22, Math.max(8, group / 4));

    data.months.forEach((month, i) => {
      const x = left + group * i + group / 2;
      const ih = ((incomeVals[i] || 0) / maxVal) * chartH;
      const eh = ((expenseVals[i] || 0) / maxVal) * chartH;

      ctx.fillStyle = "#2563eb";
      ctx.fillRect(x - bar - 2, top + chartH - ih, bar, ih);
      ctx.fillStyle = "#ef4444";
      ctx.fillRect(x + 2, top + chartH - eh, bar, eh);

      ctx.fillStyle = "#64748b";
      ctx.textAlign = "center";
      const label = month && month.length >= 7 ? month.slice(5) : month;
      ctx.fillText(label, x, height - 10);
    });

    ctx.fillStyle = "#2563eb";
    ctx.fillRect(width - 170, 12, 10, 10);
    ctx.fillStyle = "#475569";
    ctx.textAlign = "left";
    ctx.fillText("Income", width - 155, 21);

    ctx.fillStyle = "#ef4444";
    ctx.fillRect(width - 90, 12, 10, 10);
    ctx.fillStyle = "#475569";
    ctx.fillText("Expense", width - 75, 21);
  }

  renderChart();

  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(renderChart, 100);
  });
});
