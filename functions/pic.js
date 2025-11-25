// EdgeOne Pages Function
export function onRequest(context) {
  return handleRequest(context.request);
}

// 每个文件夹的图片数量（爬虫更新这个文件）
let countData = null;

async function loadCount(request) {
  if (countData) return countData;
  
  try {
    const url = new URL(request.url);
    const resp = await fetch(`${url.origin}/ri/count.json`);
    if (resp.ok) {
      countData = await resp.json();
      return countData;
    }
  } catch (e) {
    console.error('Failed to load count.json:', e);
  }
  return { vd: 0, vl: 0, hd: 0, hl: 0 };
}

// 检测是否为移动设备
function isMobileDevice(userAgent) {
  if (!userAgent) return false;
  
  var mobileKeywords = [
    'Mobile', 'Android', 'iPhone', 'iPad', 'iPod', 'BlackBerry', 
    'Windows Phone', 'Opera Mini', 'IEMobile', 'Mobile Safari',
    'webOS', 'Kindle', 'Silk', 'Fennec', 'Maemo', 'Tablet'
  ];
  
  var lowerUserAgent = userAgent.toLowerCase();
  
  for (var i = 0; i < mobileKeywords.length; i++) {
    if (lowerUserAgent.includes(mobileKeywords[i].toLowerCase())) {
      return true;
    }
  }
  
  return /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini/i.test(userAgent);
}

async function handleRequest(request) {
  try {
    var url = new URL(request.url);
    var imgType = url.searchParams.get('img');
    var jsonType = url.searchParams.get('json');
    
    // 加载数量
    var count = await loadCount(request);

    // ========== JSON 模式 ==========
    if (jsonType === 'h' || jsonType === 'v') {
      var darkFolder = jsonType + 'd';
      var lightFolder = jsonType + 'l';
      var darkCount = count[darkFolder] || 0;
      var lightCount = count[lightFolder] || 0;
      var total = darkCount + lightCount;
      
      if (total === 0) {
        return new Response(JSON.stringify({ error: '没有图片' }), {
          status: 404,
          headers: { 
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
          }
        });
      }
      
      // 随机选择
      var randomNum = Math.floor(Math.random() * total) + 1;
      var folder, fileNum, theme;
      
      if (randomNum <= darkCount) {
        folder = darkFolder;
        fileNum = randomNum;
        theme = 'dark';
      } else {
        folder = lightFolder;
        fileNum = randomNum - darkCount;
        theme = 'light';
      }
      
      var imageUrl = url.origin + '/ri/' + folder + '/' + fileNum + '.webp';
      
      return new Response(JSON.stringify({
        theme: theme,
        url: imageUrl
      }), {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'no-cache, no-store',
          'Access-Control-Allow-Origin': '*'
        }
      });
    }

    // ========== 重定向模式 ==========
    var orientation = null;
    
    if (imgType === 'h') {
      orientation = 'h';
    } else if (imgType === 'v') {
      orientation = 'v';
    } else {
      var userAgent = request.headers.get('User-Agent') || '';
      orientation = isMobileDevice(userAgent) ? 'v' : 'h';
    }
    
    var darkFolder = orientation + 'd';
    var lightFolder = orientation + 'l';
    var darkCount = count[darkFolder] || 0;
    var lightCount = count[lightFolder] || 0;
    var total = darkCount + lightCount;
    
    if (total === 0) {
      return new Response('❌ 没有图片', {
        status: 404,
        headers: { 
          'Content-Type': 'text/plain; charset=utf-8',
          'Access-Control-Allow-Origin': '*'
        }
      });
    }
    
    var randomNum = Math.floor(Math.random() * total) + 1;
    var folder, fileNum;
    
    if (randomNum <= darkCount) {
      folder = darkFolder;
      fileNum = randomNum;
    } else {
      folder = lightFolder;
      fileNum = randomNum - darkCount;
    }
    
    var imageUrl = '/ri/' + folder + '/' + fileNum + '.webp';
    
    return new Response(null, {
      status: 302,
      headers: {
        'Location': imageUrl,
        'Cache-Control': 'no-cache',
        'Access-Control-Allow-Origin': '*'
      }
    });

  } catch (error) {
    return new Response('❌ 错误: ' + error.message, {
      status: 500,
      headers: { 'Content-Type': 'text/plain; charset=utf-8' }
    });
  }
}
