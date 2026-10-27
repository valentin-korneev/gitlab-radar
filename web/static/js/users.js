function renderAuthorizedUsers() {
  const list = document.querySelector('#authorized-user-list');
  list.replaceChildren();
  if (!state.authorizedUsers.length) {
    list.append(element('p', 'empty-state', 'Список пользователей пуст.'));
    return;
  }
  state.authorizedUsers.forEach((user) => {
    const row = element('div', 'authorized-user-row');
    const summary = element('div', 'authorized-user-summary');
    summary.append(
      element('strong', '', user.preferred_username),
      element('small', '', user.source === 'environment' ? 'Администратор из окружения' : 'Пользователь Keycloak'),
    );
    row.append(summary);
    const actions = element('div', 'authorized-user-actions');
    const adminLabel = element('label', 'switch');
    const adminInput = element('input');
    adminInput.type = 'checkbox';
    adminInput.checked = user.is_admin;
    adminInput.disabled = user.source === 'environment';
    adminInput.addEventListener('change', () => updateAuthorizedUser(user, { is_admin: adminInput.checked }).catch(showError));
    adminLabel.append(adminInput, element('span'), document.createTextNode('Админ'));
    const blockedLabel = element('label', 'switch');
    const blockedInput = element('input');
    blockedInput.type = 'checkbox';
    blockedInput.checked = user.is_blocked;
    blockedInput.addEventListener('change', () => updateAuthorizedUser(user, { is_blocked: blockedInput.checked }).catch(showError));
    blockedLabel.append(blockedInput, element('span'), document.createTextNode('Заблокирован'));
    actions.append(adminLabel, blockedLabel);
    const visibility = iconButton('filter', 'secondary-button', 'Настроить фильтры пользователя');
    visibility.addEventListener('click', () => openAdminUserVisibility(user.preferred_username).catch(showError));
    actions.append(visibility);
    if (user.source === 'database') {
      const remove = iconButton('trash', 'danger-button', 'Удалить пользователя');
      remove.addEventListener('click', () => removeAuthorizedUser(user).catch(showError));
      actions.append(remove);
    }
    row.append(actions);
    list.append(row);
  });
}
async function loadAuthorizedUsersPage() {
  state.authorizedUsers = await api(API.authorizedUsers);
  renderAuthorizedUsers();
  state.loaded.users = true;
}
async function addAuthorizedUser() {
  const input = document.querySelector('#authorized-user-name');
  const user = await api(API.authorizedUsers, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ preferred_username: input.value.trim() }),
  });
  const existing = state.authorizedUsers.findIndex((item) => item.preferred_username === user.preferred_username);
  if (existing === -1) state.authorizedUsers.push(user);
  else state.authorizedUsers[existing] = user;
  state.authorizedUsers.sort((left, right) => left.preferred_username.localeCompare(right.preferred_username));
  input.value = '';
  renderAuthorizedUsers();
}
async function updateAuthorizedUser(user, changes) {
  try {
    const updated = await api(API.authorizedUsers, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        preferred_username: user.preferred_username,
        is_admin: user.is_admin,
        is_blocked: user.is_blocked,
        ...changes,
      }),
    });
    state.authorizedUsers = state.authorizedUsers.map((item) => (
      item.preferred_username === updated.preferred_username ? updated : item
    ));
  } finally {
    renderAuthorizedUsers();
  }
}
async function removeAuthorizedUser(user) {
  const confirmed = await confirmAction(
    'Удалить пользователя',
    `Запись «${user.preferred_username}» будет удалена. При следующем входе через Keycloak она появится снова.`,
    'Удалить пользователя',
  );
  if (!confirmed) return;
  await api(`${API.authorizedUsers}?preferred_username=${encodeURIComponent(user.preferred_username)}`, {
    method: 'DELETE',
  });
  state.authorizedUsers = state.authorizedUsers.filter((item) => item.preferred_username !== user.preferred_username);
  renderAuthorizedUsers();
}
