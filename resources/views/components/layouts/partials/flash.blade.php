{{-- Flash messages: session('status') as success, session('error') as danger. --}}
@if (session('status'))
    <x-ui.alert type="success" class="mb-4">{{ session('status') }}</x-ui.alert>
@endif

@if (session('error'))
    <x-ui.alert type="danger" class="mb-4">{{ session('error') }}</x-ui.alert>
@endif
