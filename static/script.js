let currentVideoInfo = null;

document.getElementById('url').addEventListener('input', debounce(async (e) => {
    const url = e.target.value.trim();
    if (!url) return;
    await fetchVideoInfo(url);
}, 500));

document.querySelectorAll('input[name="downloadType"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
        const type = e.target.value;
        if (type === 'mp3') {
            document.getElementById('qualityGroup').style.display = 'none';
            document.getElementById('audioInfo').style.display = 'block';
        } else {
            document.getElementById('qualityGroup').style.display = 'block';
            document.getElementById('audioInfo').style.display = 'none';
        }
    });
});

async function fetchVideoInfo(url) {
    const loadingDiv = document.getElementById('loading');
    const optionsPanel = document.getElementById('optionsPanel');
    const errorDiv = document.getElementById('errorMsg');
    
    loadingDiv.style.display = 'block';
    optionsPanel.style.display = 'none';
    errorDiv.style.display = 'none';
    
    try {
        const response = await fetch(`/api/info?url=${encodeURIComponent(url)}`);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || 'Failed to fetch video info');
        }
        
        currentVideoInfo = data;
        
        document.getElementById('thumbnail').src = data.thumbnail || 'https://via.placeholder.com/80x60?text=No+Thumbnail';
        document.getElementById('videoTitle').textContent = data.title;
        
        const duration = formatDuration(data.duration);
        document.getElementById('videoDetails').innerHTML = `
            <i class="fas fa-clock me-1"></i>${duration} | 
            <i class="fab fa-${data.platform} me-1"></i>${data.platform.charAt(0).toUpperCase() + data.platform.slice(1)}
        `;
        
        // Update quality options
        if (data.qualities && data.qualities.length > 0) {
            const qualitySelect = document.getElementById('quality');
            const currentValue = qualitySelect.value;
            
            qualitySelect.innerHTML = '';
            const qualityOrder = ['320p', '720p', '1080p', '2k'];
            
            for (const q of qualityOrder) {
                if (data.qualities.includes(q)) {
                    const option = document.createElement('option');
                    option.value = q;
                    let label = q;
                    if (q === '1080p') label = '1080p (Full HD)';
                    else if (q === '720p') label = '720p (HD)';
                    else if (q === '2k') label = '2K (QHD)';
                    else if (q === '320p') label = '320p (Low)';
                    option.textContent = label;
                    qualitySelect.appendChild(option);
                }
            }
        }
        
        optionsPanel.style.display = 'block';
        
    } catch (error) {
        errorDiv.style.display = 'block';
        errorDiv.textContent = `Error: ${error.message}`;
    } finally {
        loadingDiv.style.display = 'none';
    }
}

document.getElementById('downloadBtn').addEventListener('click', async () => {
    const url = document.getElementById('url').value.trim();
    const downloadType = document.querySelector('input[name="downloadType"]:checked').value;
    const quality = downloadType === 'mp4' ? document.getElementById('quality').value : '720p';
    
    if (!url) {
        showError('Please enter a video URL');
        return;
    }
    
    const downloadBtn = document.getElementById('downloadBtn');
    const originalText = downloadBtn.innerHTML;
    
    downloadBtn.disabled = true;
    downloadBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Processing...';
    
    try {
        const response = await fetch(`/api/download?url=${encodeURIComponent(url)}&quality=${quality}&type=${downloadType}`);
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Download failed');
        }
        
        const blob = await response.blob();
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = `video.${downloadType}`;
        if (contentDisposition) {
            const match = contentDisposition.match(/filename="?(.+)"?/);
            if (match) filename = match[1];
        }
        
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(downloadUrl);
        
        showSuccess('Download started!');
        
    } catch (error) {
        showError(`Download failed: ${error.message}`);
    } finally {
        downloadBtn.disabled = false;
        downloadBtn.innerHTML = originalText;
    }
});

function formatDuration(seconds) {
    if (!seconds) return 'Unknown';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    
    if (hours > 0) {
        return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function showError(message) {
    const errorDiv = document.getElementById('errorMsg');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
    setTimeout(() => {
        errorDiv.style.display = 'none';
    }, 5000);
}

function showSuccess(message) {
    const successDiv = document.createElement('div');
    successDiv.className = 'alert alert-success mt-3';
    successDiv.innerHTML = `<i class="fas fa-check-circle me-2"></i>${message}`;
    const container = document.querySelector('.card-body');
    container.appendChild(successDiv);
    setTimeout(() => {
        successDiv.remove();
    }, 3000);
}