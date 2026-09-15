(function (global) {
  'use strict';

  var WIDTH = 1080;
  var HEIGHT = 1350;
  var COLORS = {
    paper: '#F0F3F2',
    card: '#FFFFFF',
    ink: '#122A2E',
    dim: '#5A6E70',
    faint: '#8CA0A0',
    line: '#D7E0DE',
    water: '#1E6E72',
    waterWash: '#E4EFED',
    sun: '#C4703C',
    negative: '#6B687F',
    neutral: '#9694A5'
  };
  var PRE_MOOD_EN = {
    '低落': 'running on empty',
    '需要安静': 'needing quiet',
    '脑子停不下来': "thoughts won't slow down",
    '想要点灵感': 'looking for a spark',
    '累但静不下来': 'tired but wired',
    '空落落的': 'feeling hollow',
    '心里发紧': 'feeling wound tight',
    '想有人在旁边': 'wanting someone nearby',
    '想换个地方': 'needing a change of scene',
    '状态还行': 'doing okay'
  };
  var FACTOR_EN = {
    '声音舒服': 'comfortable sound', '人不多': 'few people', '坐得住': 'easy to stay',
    '光线': 'good light', '独处感': 'space to be alone', '不必消费': 'no purchase needed',
    '手上有事做': 'hands occupied', '能一直走': 'room to walk', '视野开阔': 'open view',
    '有水': 'water', '有树': 'trees', '天色刚好': 'good light outside',
    '店员舒服': 'easygoing staff', '看到没见过的': 'something new',
    '有人但不打扰': 'people, no pressure', '声音好': 'good sound', '跟着动起来': 'room to move',
    '太挤': 'too crowded', '太吵': 'too noisy', '太贵': 'too costly',
    '得跟人周旋': 'social effort', '路上太远': 'too far', '太晒 / 太亮': 'too bright',
    '不安全': 'felt unsafe'
  };

  function clean(value, maxLength) {
    var text = String(value == null ? '' : value).replace(/\s+/g, ' ').trim();
    if (!maxLength || text.length <= maxLength) return text;
    return text.slice(0, Math.max(1, maxLength - 1)).trim() + '…';
  }

  function clampScore(value) {
    var score = Number(value);
    if (!Number.isFinite(score)) return 0;
    return Math.max(-3, Math.min(3, Math.round(score)));
  }

  function signed(score) {
    return score > 0 ? '+' + score : String(score);
  }

  function scoreLabel(score, lang) {
    var zh = {
      '-3': '明显更难受', '-2': '更沉了一些', '-1': '还是有点沉',
      '0': '差不多', '1': '松了一点', '2': '明显轻了', '3': '像换了口气'
    };
    var en = {
      '-3': 'much harder', '-2': 'heavier', '-1': 'still a little heavy',
      '0': 'about the same', '1': 'a little lighter', '2': 'noticeably lighter', '3': 'a real shift'
    };
    return (lang === 'en' ? en : zh)[String(score)];
  }

  function headline(score, lang) {
    if (lang === 'en') {
      if (score > 0) return 'Today moved through this place.';
      if (score < 0) return "It didn't hold you this time — still worth remembering.";
      return 'No clear change is still part of the trail.';
    }
    if (score > 0) return '今天的情绪，走过这里。';
    if (score < 0) return '这次没接住，也是一条真实轨迹。';
    return '没有明显变化，也值得被记住。';
  }

  function dateParts(value) {
    var date = new Date(value || Date.now());
    if (Number.isNaN(date.getTime())) date = new Date();
    return {
      year: date.getFullYear(),
      month: String(date.getMonth() + 1).padStart(2, '0'),
      day: String(date.getDate()).padStart(2, '0')
    };
  }

  function buildModel(record, place, lang) {
    record = record || {};
    place = place || {};
    lang = lang === 'en' ? 'en' : 'zh';
    var score = clampScore(record.changeScore);
    var date = dateParts(record.visitStartedAt || record.createdAt);
    var factors = Array.isArray(record.factors)
      ? record.factors.map(function (item) {
          var factor = lang === 'en' ? (FACTOR_EN[item] || item) : item;
          return clean(factor, 22);
        }).filter(Boolean).slice(0, 3)
      : [];
    var dwell = Math.max(0, Math.min(1440, Math.round(Number(record.dwellMinutes) || 0)));
    var preMood = clean(record.preMood || (lang === 'en' ? 'before' : '出发前'), 24);
    if (lang === 'en') preMood = PRE_MOOD_EN[preMood] || preMood;

    return {
      lang: lang,
      date: date.year + '.' + date.month + '.' + date.day,
      isoDate: date.year + '-' + date.month + '-' + date.day,
      place: clean((lang === 'en' ? place.placeName : record.placeName) || record.placeName || place.placeName || (lang === 'en' ? 'A place on your trail' : '轨迹里的一个地方'), 38),
      category: clean((lang === 'en' ? place.category : record.placeCategory) || record.placeCategory || place.category || '', 32),
      preMood: preMood,
      score: score,
      scoreText: signed(score),
      scoreLabel: scoreLabel(score, lang),
      headline: headline(score, lang),
      factors: factors,
      dwellText: dwell
        ? (lang === 'en' ? 'stayed about ' + dwell + ' min' : '停留约 ' + dwell + ' 分钟')
        : (lang === 'en' ? 'a real visit' : '一次真实到访'),
      privacyText: lang === 'en'
        ? 'Created by you · private notes are never included'
        : '由你主动生成 · 不包含你写下的私密原话'
    };
  }

  function cardFileName(model) {
    return 'current-mood-' + model.isoDate + '.png';
  }

  function roundedRect(ctx, x, y, width, height, radius) {
    var r = Math.min(radius, width / 2, height / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + width, y, x + width, y + height, r);
    ctx.arcTo(x + width, y + height, x, y + height, r);
    ctx.arcTo(x, y + height, x, y, r);
    ctx.arcTo(x, y, x + width, y, r);
    ctx.closePath();
  }

  function textTokens(text) {
    return String(text).match(/[\u3400-\u9fff]|[^\s\u3400-\u9fff]+\s*|\s+/g) || [];
  }

  function wrapLines(ctx, text, maxWidth, maxLines) {
    var tokens = textTokens(text);
    var lines = [];
    var line = '';
    tokens.forEach(function (token) {
      var next = line + token;
      if (line && ctx.measureText(next).width > maxWidth) {
        lines.push(line.trim());
        line = token.trimStart();
      } else {
        line = next;
      }
    });
    if (line.trim()) lines.push(line.trim());
    if (maxLines && lines.length > maxLines) {
      lines = lines.slice(0, maxLines);
      var last = lines.length - 1;
      while (lines[last] && ctx.measureText(lines[last] + '…').width > maxWidth) {
        lines[last] = lines[last].slice(0, -1);
      }
      lines[last] = lines[last].trim() + '…';
    }
    return lines;
  }

  function drawLines(ctx, lines, x, y, lineHeight) {
    lines.forEach(function (line, index) { ctx.fillText(line, x, y + index * lineHeight); });
  }

  function scoreColor(score) {
    if (score > 0) return COLORS.water;
    if (score < 0) return COLORS.negative;
    return COLORS.neutral;
  }

  function drawCard(model, options) {
    options = options || {};
    var doc = options.document || global.document;
    if (!doc || !doc.createElement) throw new Error('当前浏览器无法生成图片');
    var canvas = doc.createElement('canvas');
    canvas.width = WIDTH;
    canvas.height = HEIGHT;
    var ctx = canvas.getContext && canvas.getContext('2d');
    if (!ctx) throw new Error('当前浏览器无法生成图片');

    ctx.fillStyle = COLORS.paper;
    ctx.fillRect(0, 0, WIDTH, HEIGHT);

    ctx.save();
    ctx.globalAlpha = 0.12;
    ctx.strokeStyle = COLORS.water;
    ctx.lineWidth = 2;
    [260, 360, 470].forEach(function (radius) {
      ctx.beginPath();
      ctx.arc(920, 80, radius, 0, Math.PI * 2);
      ctx.stroke();
    });
    ctx.restore();

    ctx.fillStyle = COLORS.card;
    roundedRect(ctx, 58, 54, 964, 1242, 42);
    ctx.fill();
    ctx.strokeStyle = COLORS.line;
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.fillStyle = COLORS.ink;
    ctx.font = '500 28px "Helvetica Neue", "PingFang SC", sans-serif';
    ctx.fillText(model.lang === 'en' ? 'CURRENT' : '此在 · CURRENT', 112, 132);
    ctx.textAlign = 'right';
    ctx.fillStyle = COLORS.faint;
    ctx.font = '24px "IBM Plex Mono", monospace';
    ctx.fillText(model.date, 968, 132);
    ctx.textAlign = 'left';

    ctx.fillStyle = COLORS.ink;
    ctx.font = '400 62px "Songti SC", "Noto Serif SC", serif';
    var headingLines = wrapLines(ctx, model.headline, 820, 2);
    drawLines(ctx, headingLines, 112, 258, 82);

    ctx.fillStyle = COLORS.water;
    ctx.font = '500 25px "Helvetica Neue", "PingFang SC", sans-serif';
    ctx.fillText(model.lang === 'en' ? 'THE PLACE' : '这次经过的空间', 112, 430);
    ctx.fillStyle = COLORS.ink;
    ctx.font = '400 43px "Songti SC", "Noto Serif SC", serif';
    drawLines(ctx, wrapLines(ctx, model.place, 820, 2), 112, 488, 54);
    if (model.category) {
      ctx.fillStyle = COLORS.dim;
      ctx.font = '25px "Helvetica Neue", "PingFang SC", sans-serif';
      ctx.fillText(model.category, 112, 586);
    }

    ctx.strokeStyle = COLORS.line;
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(160, 755);
    ctx.bezierCurveTo(360, 695, 570, 815, 810, 720);
    ctx.stroke();

    ctx.fillStyle = COLORS.sun;
    ctx.beginPath();
    ctx.arc(160, 755, 13, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = scoreColor(model.score);
    ctx.beginPath();
    ctx.arc(810, 720, 22, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = COLORS.faint;
    ctx.font = '22px "IBM Plex Mono", monospace';
    ctx.fillText(model.lang === 'en' ? 'BEFORE' : '出发前', 112, 625);
    ctx.fillStyle = COLORS.ink;
    ctx.font = '400 36px "Songti SC", "Noto Serif SC", serif';
    drawLines(ctx, wrapLines(ctx, model.preMood, 330, 2), 112, 670, 44);

    ctx.textAlign = 'right';
    ctx.fillStyle = COLORS.faint;
    ctx.font = '22px "IBM Plex Mono", monospace';
    ctx.fillText(model.lang === 'en' ? 'AFTER' : '离开后', 968, 615);
    ctx.fillStyle = scoreColor(model.score);
    ctx.font = '500 82px "IBM Plex Mono", monospace';
    ctx.fillText(model.scoreText, 968, 700);
    ctx.font = '400 34px "Songti SC", "Noto Serif SC", serif';
    ctx.fillText(model.scoreLabel, 968, 785);
    ctx.textAlign = 'left';

    ctx.fillStyle = COLORS.faint;
    ctx.font = '22px "IBM Plex Mono", monospace';
    ctx.fillText(model.lang === 'en' ? 'WHAT WAS THERE' : '参与变化的因素', 112, 850);

    var chipX = 112;
    var chipY = 886;
    var factors = model.factors.length ? model.factors : [model.lang === 'en' ? 'nothing selected' : '没有勾选'];
    ctx.font = '500 27px "Helvetica Neue", "PingFang SC", sans-serif';
    factors.forEach(function (factor) {
      var chipWidth = Math.min(340, ctx.measureText(factor).width + 54);
      if (chipX + chipWidth > 968) {
        chipX = 112;
        chipY += 68;
      }
      ctx.fillStyle = COLORS.waterWash;
      roundedRect(ctx, chipX, chipY, chipWidth, 50, 25);
      ctx.fill();
      ctx.fillStyle = COLORS.water;
      ctx.fillText(factor, chipX + 27, chipY + 34);
      chipX += chipWidth + 14;
    });

    ctx.fillStyle = COLORS.ink;
    ctx.font = '400 35px "Songti SC", "Noto Serif SC", serif';
    ctx.fillText(model.dwellText, 112, 1038);
    ctx.fillStyle = COLORS.dim;
    ctx.font = '24px "Helvetica Neue", "PingFang SC", sans-serif';
    ctx.fillText(model.lang === 'en' ? 'A change in you, not a rating of the place.' : '这是同一个人前后的差，不是这个地方的星级。', 112, 1084);

    ctx.fillStyle = COLORS.paper;
    roundedRect(ctx, 96, 1134, 888, 80, 20);
    ctx.fill();
    ctx.fillStyle = COLORS.dim;
    ctx.font = '23px "Helvetica Neue", "PingFang SC", sans-serif';
    ctx.fillText(model.privacyText, 124, 1183);

    ctx.fillStyle = COLORS.faint;
    ctx.font = '21px "IBM Plex Mono", monospace';
    ctx.fillText('CURRENT · MOOD × PLACE × VISIT', 112, 1260);
    ctx.fillStyle = COLORS.sun;
    ctx.beginPath();
    ctx.arc(958, 1252, 9, 0, Math.PI * 2);
    ctx.fill();

    return canvas;
  }

  function dataUrlToBlob(dataUrl, options) {
    options = options || {};
    var parts = String(dataUrl).split(',');
    if (parts.length !== 2) throw new Error('图片生成失败');
    var typeMatch = parts[0].match(/data:([^;]+)/);
    var type = typeMatch ? typeMatch[1] : 'image/png';
    var decode = options.atob || global.atob;
    if (!decode) throw new Error('当前浏览器无法导出图片');
    var binary = decode(parts[1]);
    var bytes = new Uint8Array(binary.length);
    for (var index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return new Blob([bytes], { type: type });
  }

  function createArtifact(record, place, options) {
    options = options || {};
    var model = buildModel(record, place, options.lang);
    var canvas = drawCard(model, options);
    var blob = dataUrlToBlob(canvas.toDataURL('image/png'), options);
    return { model: model, blob: blob, fileName: cardFileName(model), canvas: canvas };
  }

  function saveBlob(blob, fileName, options) {
    options = options || {};
    var doc = options.document || global.document;
    var urlApi = options.URL || global.URL;
    if (!doc || !doc.createElement || !urlApi || !urlApi.createObjectURL) {
      throw new Error('当前浏览器无法保存图片');
    }
    var href = urlApi.createObjectURL(blob);
    var anchor = doc.createElement('a');
    anchor.href = href;
    anchor.download = fileName;
    anchor.rel = 'noopener';
    if (doc.body && doc.body.appendChild) doc.body.appendChild(anchor);
    anchor.click();
    if (anchor.remove) anchor.remove();
    (options.setTimeout || global.setTimeout)(function () { urlApi.revokeObjectURL(href); }, 1000);
  }

  function save(record, place, options) {
    var artifact = createArtifact(record, place, options);
    saveBlob(artifact.blob, artifact.fileName, options);
    return { method: 'download', fileName: artifact.fileName };
  }

  function share(record, place, options) {
    options = options || {};
    var artifact = createArtifact(record, place, options);
    var nav = options.navigator || global.navigator || {};
    var FileCtor = options.File || global.File;
    var file = FileCtor ? new FileCtor([artifact.blob], artifact.fileName, { type: 'image/png' }) : null;
    var payload = file ? {
      files: [file],
      title: artifact.model.lang === 'en' ? 'My Current trail' : '我的此在 · 心情轨迹',
      text: artifact.model.place + ' · ' + artifact.model.scoreLabel + ' ' + artifact.model.scoreText
    } : null;
    var canShare = false;
    try {
      canShare = Boolean(payload && nav.share && nav.canShare && nav.canShare({ files: payload.files }));
    } catch (_) {}

    if (!canShare) {
      saveBlob(artifact.blob, artifact.fileName, options);
      return Promise.resolve({ method: 'download', fileName: artifact.fileName });
    }

    // navigator.share 必须直接发生在点击事件里。上面的 canvas 与 Blob 生成都是同步的，
    // 此处之前不能插入 await，否则 iOS 会认为用户手势已经结束。
    var shared;
    try {
      shared = nav.share(payload);
    } catch (error) {
      if (error && error.name === 'AbortError') {
        return Promise.resolve({ method: 'cancelled', fileName: artifact.fileName });
      }
      saveBlob(artifact.blob, artifact.fileName, options);
      return Promise.resolve({ method: 'download', fileName: artifact.fileName, reason: error && error.message });
    }
    return Promise.resolve(shared).then(function () {
      return { method: 'share', fileName: artifact.fileName };
    }).catch(function (error) {
      if (error && error.name === 'AbortError') return { method: 'cancelled', fileName: artifact.fileName };
      saveBlob(artifact.blob, artifact.fileName, options);
      return { method: 'download', fileName: artifact.fileName, reason: error && error.message };
    });
  }

  global.CurrentMoodCard = {
    buildModel: buildModel,
    cardFileName: cardFileName,
    wrapLines: wrapLines,
    drawCard: drawCard,
    createArtifact: createArtifact,
    save: save,
    share: share,
    dimensions: { width: WIDTH, height: HEIGHT }
  };
})(typeof window !== 'undefined' ? window : globalThis);
