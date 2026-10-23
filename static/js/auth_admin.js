const BASE_PATH = window.location.pathname.startsWith('/auth') ? '/auth' : '';



// Проверка ответа на 401
function checkAuthResponse(response) {
    if (response.status === 401) {
        window.location.href = `${BASE_PATH}/login`;
        return false;
    }
    return true;
}



// Загрузка списка пользователей
async function loadUsers() {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return; // Если вошел обычный сотрудник, таблицы нет
    
    try {
        const response = await fetch(`${BASE_PATH}/api/users?_=${new Date().getTime()}`);
        if (!checkAuthResponse(response)) return;
        
        const allUsers = await response.json();
        renderUsers(allUsers);
    } catch (error) {
        console.error("Ошибка загрузки пользователей:", error);
    }
}

// Глобальная переменная для роли нового пользователя
let selectedNewUserRole = 'employee';

// Создание кастомного выпадающего списка
function createCustomDropdown(options, defaultValue, onChange) {
    const wrapper = document.createElement('div');
    wrapper.className = 'custom-select-wrapper';
    
    const trigger = document.createElement('div');
    trigger.className = 'custom-select-trigger';
    const selectedOption = options.find(opt => opt.value === defaultValue) || options[0];
    trigger.innerText = selectedOption.label;
    wrapper.appendChild(trigger);
    
    const optionsContainer = document.createElement('div');
    optionsContainer.className = 'custom-select-options glass';
    
    options.forEach(opt => {
        const optDiv = document.createElement('div');
        optDiv.className = `custom-option ${opt.value === defaultValue ? 'selected' : ''}`;
        optDiv.innerText = opt.label;
        optDiv.onclick = (e) => {
            e.stopPropagation();
            trigger.innerText = opt.label;
            optionsContainer.querySelectorAll('.custom-option').forEach(el => el.classList.remove('selected'));
            optDiv.classList.add('selected');
            optionsContainer.classList.remove('open');
            wrapper.classList.remove('open');
            onChange(opt.value);
        };
        optionsContainer.appendChild(optDiv);
    });
    
    wrapper.appendChild(optionsContainer);
    
    trigger.onclick = (e) => {
        e.stopPropagation();
        // Закрываем все остальные открытые выпадающие списки
        document.querySelectorAll('.custom-select-wrapper').forEach(el => {
            if (el !== wrapper) {
                el.classList.remove('open');
                el.querySelector('.custom-select-options').classList.remove('open');
            }
        });
        wrapper.classList.toggle('open');
        optionsContainer.classList.toggle('open');
    };
    
    return wrapper;
}

// Глобальный обработчик клика для закрытия всех списков при клике мимо
document.addEventListener('click', () => {
    document.querySelectorAll('.custom-select-wrapper').forEach(el => {
        el.classList.remove('open');
        const opts = el.querySelector('.custom-select-options');
        if (opts) opts.classList.remove('open');
    });
});

// Инициализация основного выбора роли
function initMainRoleSelector() {
    const container = document.getElementById('roleSelectWrapper');
    if (!container) return;
    container.innerHTML = '';
    
    const dropdown = createCustomDropdown([
        { value: 'employee', label: 'Сотрудник' },
        { value: 'admin', label: 'Администратор' }
    ], 'employee', (value) => {
        selectedNewUserRole = value;
    });
    
    container.appendChild(dropdown);
}

// Отрисовка таблицы пользователей
function renderUsers(users) {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (users.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="table-empty-msg">Пользователи не найдены</td></tr>`;
        return;
    }

    users.forEach(user => {
        const safeName = user.username.replace(/['"]/g, '');
        const safeDisplayName = (user.display_name || '').replace(/['"]/g, '');
        const row = document.createElement('tr');
        row.className = 'user-row';
        
        // 1. Имя пользователя и отображаемое имя (displayName)
        const tdName = document.createElement('td');
        tdName.className = 'cell-user';
        tdName.setAttribute('data-label', 'Пользователь');
        let nameHtml = `<div class="user-cell-name">${safeName}</div>`;
        if (safeDisplayName && safeDisplayName.toLowerCase() !== safeName.toLowerCase()) {
            nameHtml += `<div class="user-cell-display">${safeDisplayName}</div>`;
        }
        tdName.innerHTML = nameHtml;
        row.appendChild(tdName);

        // 2. Источник учетной записи (Active Directory / Локальный)
        const tdSource = document.createElement('td');
        tdSource.className = 'cell-source';
        tdSource.setAttribute('data-label', 'Источник');
        if (user.auth_source === 'ldap') {
            tdSource.innerHTML = `<span class="service-status-badge source-badge ldap-badge">🌐 Active Directory</span>`;
        } else {
            tdSource.innerHTML = `<span class="service-status-badge source-badge local-badge">🖥️ Локальный</span>`;
        }
        row.appendChild(tdSource);
        
        // 3. Роль (кастомный селект с сохранением в БД)
        const tdRole = document.createElement('td');
        tdRole.className = 'cell-role';
        tdRole.setAttribute('data-label', 'Роль');
        if (user.username === CURRENT_USERNAME) {
            tdRole.innerHTML = `<span class="status-badge active">${user.role === 'admin' ? 'Администратор' : 'Сотрудник'} <span class="current-user-tag">(Вы)</span></span>`;
        } else {
            tdRole.classList.add('table-cell-dropdown');
            const dropdown = createCustomDropdown([
                { value: 'employee', label: 'Сотрудник' },
                { value: 'admin', label: 'Администратор' }
            ], user.role, (value) => {
                updateUserRole(user.id, value);
            });
            tdRole.appendChild(dropdown);
        }
        row.appendChild(tdRole);
        
        // 4. Дата создания / первого входа
        const tdDate = document.createElement('td');
        tdDate.className = 'cell-date';
        tdDate.setAttribute('data-label', 'Создан');
        tdDate.innerText = user.created_at || '—';
        row.appendChild(tdDate);
        
        // 5. Действия (Сброс пароля для локальных / бейдж для AD + удаление)
        const tdActions = document.createElement('td');
        tdActions.className = 'cell-actions text-right';
        tdActions.setAttribute('data-label', 'Действия');
        
        let actionsHtml = '';
        if (user.auth_source === 'ldap') {
            actionsHtml += `<span class="btn-action-disabled" title="Пароль управляется в домене Active Directory">🔐 Доменный</span>`;
        } else {
            actionsHtml += `<button onclick="openResetModal(${user.id}, '${safeName}')" class="btn-action-reset" title="Сбросить пароль пользователя">🔑 Сброс пароля</button>`;
        }
        
        if (user.username === CURRENT_USERNAME) {
            actionsHtml += `<span class="current-user-tag-btn">Текущий</span>`;
        } else {
            actionsHtml += `<button onclick="deleteUser(${user.id}, '${safeName}')" class="btn-action-revoke" title="Удалить аккаунт">Удалить</button>`;
        }
        tdActions.innerHTML = actionsHtml;
        row.appendChild(tdActions);
        
        tbody.appendChild(row);
    });
}

// Изменение роли пользователя
async function updateUserRole(userId, newRole) {
    try {
        const response = await fetch(`${BASE_PATH}/api/users/update-role/${userId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role: newRole })
        });
        
        if (!checkAuthResponse(response)) return;
        const result = await response.json();
        
        if (!response.ok) {
            alert(`Ошибка изменения роли: ${result.error}`);
            loadUsers();
        }
    } catch (err) {
        alert("Ошибка соединения с сервером");
        loadUsers();
    }
}

// Создание пользователя
async function createUser() {
    const userInp = document.getElementById('newUsername');
    const passInp = document.getElementById('newPassword');
    const username = userInp.value.trim();
    const password = passInp.value.trim();
    const role = selectedNewUserRole;
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
            initMainRoleSelector(); // Сбрасываем селект на "Сотрудник"
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
function initThemeToggle() {
    const themeToggleBtn = document.getElementById('theme-toggle');
    if (!themeToggleBtn) return;
    
    const sunIcon = themeToggleBtn.querySelector('.sun-icon');
    const moonIcon = themeToggleBtn.querySelector('.moon-icon');

    if (document.documentElement.classList.contains('light-theme')) {
        sunIcon.classList.add('hidden');
        moonIcon.classList.remove('hidden');
    }

    themeToggleBtn.addEventListener('click', () => {
        document.documentElement.classList.toggle('light-theme');
        const isLight = document.documentElement.classList.contains('light-theme');
        localStorage.setItem('theme', isLight ? 'light' : 'dark');
        
        if (isLight) {
            sunIcon.classList.add('hidden');
            moonIcon.classList.remove('hidden');
        } else {
            sunIcon.classList.remove('hidden');
            moonIcon.classList.add('hidden');
        }
    });
}

// Управление цветовой палитрой оформления
function initPalettePicker() {
    const savedPalette = localStorage.getItem('theme_palette') || 'classic';
    document.documentElement.setAttribute('data-palette', savedPalette);

    const toggleBtn = document.getElementById('palette-toggle-btn');
    const menu = document.getElementById('paletteMenu');
    if (!toggleBtn || !menu) return;

    function updateActiveOption(palette) {
        menu.querySelectorAll('.palette-option').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.paletteVal === palette);
        });
    }
    updateActiveOption(savedPalette);

    toggleBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        menu.classList.toggle('hidden');
    });

    document.addEventListener('click', (e) => {
        if (!menu.contains(e.target) && !toggleBtn.contains(e.target)) {
            menu.classList.add('hidden');
        }
    });

    menu.querySelectorAll('.palette-option').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const palette = btn.dataset.paletteVal;
            document.documentElement.setAttribute('data-palette', palette);
            localStorage.setItem('theme_palette', palette);
            updateActiveOption(palette);
            menu.classList.add('hidden');
        });
    });
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

// Управление сбросом пароля локальных пользователей администратором
let currentResetUserId = null;

function openResetModal(userId, username) {
    currentResetUserId = userId;
    const modal = document.getElementById('resetPasswordModal');
    const userLabel = document.getElementById('resetModalUsername');
    const passwordInput = document.getElementById('resetModalNewPassword');
    const statusMsg = document.getElementById('resetModalStatus');
    
    if (userLabel) userLabel.innerText = username;
    if (passwordInput) passwordInput.value = '';
    if (statusMsg) {
        statusMsg.style.display = 'none';
        statusMsg.innerText = '';
    }
    if (modal) modal.style.display = 'flex';
}

function closeResetModal() {
    currentResetUserId = null;
    const modal = document.getElementById('resetPasswordModal');
    if (modal) modal.style.display = 'none';
}

function generateRandomPassword() {
    const chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%&*";
    let password = "";
    for (let i = 0; i < 12; i++) {
        password += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    const input = document.getElementById('resetModalNewPassword');
    if (input) input.value = password;
}

async function confirmResetPassword() {
    if (!currentResetUserId) return;
    const passwordInput = document.getElementById('resetModalNewPassword');
    const statusMsg = document.getElementById('resetModalStatus');
    const newPassword = passwordInput ? passwordInput.value.trim() : '';
    
    if (!newPassword || newPassword.length < 4) {
        if (statusMsg) {
            statusMsg.style.display = 'block';
            statusMsg.className = 'status-msg error';
            statusMsg.innerText = 'Пароль должен содержать минимум 4 символа';
        }
        return;
    }
    
    try {
        const response = await fetch(`${BASE_PATH}/api/users/reset-password/${currentResetUserId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_password: newPassword })
        });
        
        if (!checkAuthResponse(response)) return;
        const result = await response.json();
        
        if (response.ok && result.success) {
            if (statusMsg) {
                statusMsg.style.display = 'block';
                statusMsg.className = 'status-msg success';
                statusMsg.innerText = result.message || 'Пароль успешно обновлен!';
            }
            setTimeout(() => {
                closeResetModal();
            }, 1200);
        } else {
            if (statusMsg) {
                statusMsg.style.display = 'block';
                statusMsg.className = 'status-msg error';
                statusMsg.innerText = result.error || 'Ошибка сброса пароля';
            }
        }
    } catch (e) {
        if (statusMsg) {
            statusMsg.style.display = 'block';
            statusMsg.className = 'status-msg error';
            statusMsg.innerText = 'Ошибка соединения с сервером';
        }
    }
}

// Управление шириной рабочей области (Компактный 1440px / На всю ширину 100%)
function initLayoutToggle() {
    const layoutToggle = document.getElementById('layout-toggle');
    if (!layoutToggle) return;

    function updateLayoutIcons(isFull) {
        const expandIcon = layoutToggle.querySelector('.expand-icon');
        const compressIcon = layoutToggle.querySelector('.compress-icon');
        if (isFull) {
            layoutToggle.title = 'Компактный вид (1440px)';
            if (expandIcon) expandIcon.classList.add('hidden');
            if (compressIcon) compressIcon.classList.remove('hidden');
        } else {
            layoutToggle.title = 'На всю ширину (100%)';
            if (expandIcon) expandIcon.classList.remove('hidden');
            if (compressIcon) compressIcon.classList.add('hidden');
        }
    }

    const isFullInitial = localStorage.getItem('layout_width') === 'full';
    if (isFullInitial) {
        document.body.classList.add('layout-fullwidth');
        document.documentElement.classList.add('layout-fullwidth');
    }
    updateLayoutIcons(isFullInitial);

    layoutToggle.addEventListener('click', () => {
        const isFull = document.body.classList.contains('layout-fullwidth');
        if (isFull) {
            document.body.classList.remove('layout-fullwidth');
            document.documentElement.classList.remove('layout-fullwidth');
            localStorage.setItem('layout_width', 'compact');
            updateLayoutIcons(false);
        } else {
            document.body.classList.add('layout-fullwidth');
            document.documentElement.classList.add('layout-fullwidth');
            localStorage.setItem('layout_width', 'full');
            updateLayoutIcons(true);
        }
    });
}

window.onload = function() {
    loadUsers();
    initThemeToggle();
    initPalettePicker();
    initLayoutToggle();
    initMainRoleSelector();
};
