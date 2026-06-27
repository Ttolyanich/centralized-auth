const BASE_PATH = window.location.pathname.startsWith('/openvpn') ? '/openvpn' : '';

let allUsers = [];

// Проверка ответа на 401
function checkAuthResponse(response) {
    if (response.status === 401) {
        window.location.href = `${BASE_PATH}/login`;
        return false;
    }
    return true;
}

// Загрузка текущего имени
function loadCurrentUserName() {
    // Отображение имени теперь происходит на стороне сервера через Jinja2 шаблонизатор
}

// Загрузка списка пользователей
async function loadUsers() {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return; // Если вошел обычный сотрудник, таблицы нет
    
    try {
        const response = await fetch(`${BASE_PATH}/api/users?_=${new Date().getTime()}`);
        if (!checkAuthResponse(response)) return;
        
        allUsers = await response.json();
        renderUsers(allUsers);
    } catch (error) {
        console.error("Ошибка загрузки пользователей:", error);
    }
}

// Отрисовка таблицы пользователей
function renderUsers(users) {
    const tbody = document.getElementById('usersTableBody');
    tbody.innerHTML = '';

    if (users.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:32px; color:#888;">Пользователи не найдены</td></tr>`;
        return;
    }

    users.forEach(user => {
        const safeName = user.username.replace(/['"]/g, '');
        const deleteButton = `<button onclick="deleteUser(${user.id}, '${safeName}')" class="btn-action-revoke">Удалить</button>`;

        const row = document.createElement('tr');
        row.innerHTML = `
            <td style="font-family:monospace; font-weight:600; padding:14px 24px;">${safeName}</td>
            <td style="padding:14px 24px;"><span class="status-badge active">${user.role}</span></td>
            <td style="padding:14px 24px; color: #888;">${user.created_at}</td>
            <td class="text-right" style="padding:14px 24px;">${deleteButton}</td>
        `;
        tbody.appendChild(row);
    });
}

// Создание пользователя
async function createUser() {
    const userInp = document.getElementById('newUsername');
    const passInp = document.getElementById('newPassword');
    const roleInp = document.getElementById('newRole');
    const username = userInp.value.trim();
    const password = passInp.value.trim();
    const role = roleInp ? roleInp.value : 'employee';
    const msg = document.getElementById('actionMessage');

    if (!username || !password) {
        msg.style.color = "#ef4444";
        msg.style.display = "block";
        msg.innerText = "Заполните все поля";
        return;
    }

    msg.style.color = "#2563eb";
    msg.style.display = "block";
    msg.innerText = "Создание пользователя...";

    try {
        const response = await fetch(`${BASE_PATH}/api/users`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify({ username: username, password: password, role: role })
        });
        
        if (!checkAuthResponse(response)) return;
        const result = await response.json();
        
        if (response.ok) {
            msg.style.color = "#10b981";
            msg.innerText = `Пользователь ${username} успешно добавлен.`;
            userInp.value = '';
            passInp.value = '';
            loadUsers();
        } else {
            msg.style.color = "#ef4444";
            msg.innerText = `Ошибка: ${result.error}`;
        }
    } catch (err) {
        msg.style.color = "#ef4444";
        msg.innerText = "Ошибка соединения с сервером.";
    }
}

// Удаление пользователя
async function deleteUser(userId, name) {
    if (!confirm(`Вы действительно хотите удалить пользователя ${name}?`)) return;
    
    try {
        const response = await fetch(`${BASE_PATH}/api/users/delete/${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!checkAuthResponse(response)) return;
        
        if (response.ok) {
            loadUsers();
        } else {
            const res = await response.json();
            alert("Ошибка при удалении: " + res.error);
        }
    } catch (err) {
        alert("Ошибка связи с сервером.");
    }
}

// Выход из системы
async function handleLogout() {
    try {
        const response = await fetch(`${BASE_PATH}/logout`, {
            method: 'POST'
        });
        if (response.ok) {
            window.location.href = `${BASE_PATH}/login`;
        }
    } catch {
        alert('Ошибка связи при выходе');
    }
}

// Управление темой оформления
function initTheme() {
    updateThemeIcon();
}

function updateThemeIcon() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const themeIcon = document.getElementById('themeIcon');
    if (!themeIcon) return;
    
    if (currentTheme === 'light') {
        themeIcon.innerHTML = '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path>';
    } else {
        themeIcon.innerHTML = '<circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"></path>';
    }
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    updateThemeIcon();
}

// Функция смены пароля
async function changePassword() {
    const oldInp = document.getElementById('oldPassword');
    const newInp = document.getElementById('newPasswordSelf');
    const confirmInp = document.getElementById('confirmPasswordSelf');
    const msg = document.getElementById('passwordMessage');
    
    const oldPassword = oldInp.value;
    const newPassword = newInp.value;
    const confirmPassword = confirmInp.value;
    
    if (!oldPassword || !newPassword || !confirmPassword) {
        msg.style.color = "#ef4444";
        msg.style.display = "block";
        msg.innerText = "Заполните все поля";
        return;
    }
    
    if (newPassword !== confirmPassword) {
        msg.style.color = "#ef4444";
        msg.style.display = "block";
        msg.innerText = "Новые пароли не совпадают";
        return;
    }
    
    msg.style.color = "#2563eb";
    msg.style.display = "block";
    msg.innerText = "Смена пароля...";
    
    try {
        const response = await fetch(`${BASE_PATH}/api/users/change-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_password: oldPassword, new_password: newPassword })
        });
        
        if (!checkAuthResponse(response)) return;
        const result = await response.json();
        
        if (response.ok) {
            msg.style.color = "#10b981";
            msg.innerText = "Пароль успешно изменен";
            oldInp.value = '';
            newInp.value = '';
            confirmInp.value = '';
        } else {
            msg.style.color = "#ef4444";
            msg.innerText = `Ошибка: ${result.error}`;
        }
    } catch (err) {
        msg.style.color = "#ef4444";
        msg.innerText = "Ошибка соединения с сервером";
    }
}

window.onload = function() {
    loadCurrentUserName();
    loadUsers();
    initTheme();
};
