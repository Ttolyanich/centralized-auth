const BASE_PATH = window.location.pathname.startsWith('/openvpn') ? '/openvpn' : '';



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
        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:32px; color:#888;">Пользователи не найдены</td></tr>`;
        return;
    }

    users.forEach(user => {
        const safeName = user.username.replace(/['"]/g, '');
        const row = document.createElement('tr');
        
        // Имя пользователя
        const tdName = document.createElement('td');
        tdName.style.fontFamily = 'monospace';
        tdName.style.fontWeight = '600';
        tdName.style.padding = '14px 24px';
        tdName.innerText = safeName;
        row.appendChild(tdName);
        
        // Роль (кастомный селект)
        const tdRole = document.createElement('td');
        tdRole.style.padding = '14px 24px';
        if (user.username === CURRENT_USERNAME) {
            tdRole.innerHTML = `<span class="status-badge active">${user.role === 'admin' ? 'Администратор' : 'Сотрудник'}</span>`;
        } else {
            tdRole.className = 'table-cell-dropdown';
            const dropdown = createCustomDropdown([
                { value: 'employee', label: 'Сотрудник' },
                { value: 'admin', label: 'Администратор' }
            ], user.role, (value) => {
                updateUserRole(user.id, value);
            });
            tdRole.appendChild(dropdown);
        }
        row.appendChild(tdRole);
        
        // Дата создания
        const tdDate = document.createElement('td');
        tdDate.style.padding = '14px 24px';
        tdDate.style.color = '#888';
        tdDate.innerText = user.created_at;
        row.appendChild(tdDate);
        
        // Действия (Нельзя удалить самого себя)
        const tdActions = document.createElement('td');
        tdActions.className = 'text-right';
        tdActions.style.padding = '14px 24px';
        if (user.username === CURRENT_USERNAME) {
            tdActions.innerHTML = `<span style="color:#666; font-size:12px; padding: 6px 12px; display:inline-block;">Текущий</span>`;
        } else {
            tdActions.innerHTML = `<button onclick="deleteUser(${user.id}, '${safeName}')" class="btn-action-revoke">Удалить</button>`;
        }
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
    loadUsers();
    initThemeToggle();
    initMainRoleSelector();
};
