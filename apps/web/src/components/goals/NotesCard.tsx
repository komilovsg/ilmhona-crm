"use client";

import { useState } from "react";
import { Button } from "@heroui/button";
import { Chip } from "@heroui/chip";
import { Input, Textarea } from "@heroui/input";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { AppModal } from "@/components/AppModal";
import { ConfirmModal } from "@/components/ConfirmModal";
import { ConflictDialog } from "@/components/ConflictDialog";
import { Icon } from "@/components/Icon";
import { LoadingButton } from "@/components/LoadingButton";
import { EmptyState, QueryState } from "@/components/QueryState";
import { SelectField } from "@/components/SelectField";
import { Bone } from "@/components/Skeletons";
import { useGoals, useNotes } from "@/hooks/goals";
import { useCourses } from "@/hooks/education";
import { useFieldErrors } from "@/hooks/useFieldErrors";
import { useVersionedSave } from "@/hooks/useVersionedSave";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { charsLeft, isSaveShortcut, NOTE_TEXT_MAX, type Note } from "@/lib/goals";
import { useSubmit } from "@/lib/submit";
import { notify, notifyError } from "@/lib/toast";

type Links = { goal_id: string | null; course_id: string | null; cohort_id: string | null };
const NO_LINKS: Links = { goal_id: null, course_id: null, cohort_id: null };

type CohortOption = { id: string; code: string; course_name: string };

function useCohortOptions(enabled: boolean) {
  return useQuery({
    queryKey: ["note-cohorts"],
    queryFn: () => api<{ items: CohortOption[] }>("/api/v1/cohorts", { params: { page_size: "100" } }),
    enabled,
    staleTime: 5 * 60_000,
  });
}

/** Three optional links of a note: goal, course, cohort. Options load when the pickers are first shown. */
function LinkPickers({ value, onChange }: { value: Links; onChange: (v: Links) => void }) {
  const goals = useGoals(false);
  const courses = useCourses();
  const cohorts = useCohortOptions(true);

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <SelectField
        allLabel="Без цели"
        label="Цель"
        options={(goals.data?.items ?? []).map((g) => ({ key: g.id, label: g.title }))}
        value={value.goal_id}
        onChange={(goal_id) => onChange({ ...value, goal_id })}
      />
      <SelectField
        allLabel="Без курса"
        label="Курс"
        options={(courses.data ?? []).map((c) => ({ key: c.id, label: c.name }))}
        value={value.course_id}
        onChange={(course_id) => onChange({ ...value, course_id })}
      />
      <SelectField
        allLabel="Без потока"
        label="Поток"
        options={(cohorts.data?.items ?? []).map((c) => ({ key: c.id, label: `${c.code} · ${c.course_name}` }))}
        value={value.cohort_id}
        onChange={(cohort_id) => onChange({ ...value, cohort_id })}
      />
    </div>
  );
}

function useRefreshNotes() {
  const queryClient = useQueryClient();

  return () => Promise.all([queryClient.invalidateQueries({ queryKey: ["notes"] }), queryClient.invalidateQueries({ queryKey: ["goals"] })]);
}

function LinkChips({ note }: { note: Note }) {
  const chips = [
    note.goal_title && { key: "g", label: `Цель: ${note.goal_title}` },
    note.course_name && { key: "c", label: `Курс: ${note.course_name}` },
    note.cohort_code && { key: "h", label: `Поток: ${note.cohort_code}` },
  ].filter((c): c is { key: string; label: string } => !!c);

  if (!chips.length) return null;

  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {chips.map((c) => (
        <Chip key={c.key} size="sm" variant="flat">
          {c.label}
        </Chip>
      ))}
    </div>
  );
}

function EditNoteModal({ note, onClose }: { note: Note; onClose: () => void }) {
  const refresh = useRefreshNotes();
  const [text, setText] = useState(note.text);
  const [links, setLinks] = useState<Links>({ goal_id: note.goal_id, course_id: note.course_id, cohort_id: note.cohort_id });
  const values = { text: text.trim(), ...links };

  const save = useVersionedSave({
    record: note,
    values,
    toValues: (n: Note) => ({ text: n.text, goal_id: n.goal_id, course_id: n.course_id, cohort_id: n.cohort_id }),
    apply: (v) => {
      setText(v.text);
      setLinks({ goal_id: v.goal_id, course_id: v.course_id, cohort_id: v.cohort_id });
    },
    request: (changed, version) => api<Note>(`/api/v1/notes/${note.id}`, { method: "PATCH", body: changed, version }),
    labels: { text: "Текст", goal_id: "Цель", course_id: "Курс", cohort_id: "Поток" },
    show: { text: (t: string) => t, goal_id: (g: string | null) => (g ? "выбрана" : "нет"), course_id: (c: string | null) => (c ? "выбран" : "нет"), cohort_id: (c: string | null) => (c ? "выбран" : "нет") },
    onSaved: () => {
      void refresh();
      notify("Заметка сохранена");
      onClose();
    },
  });
  const fe = useFieldErrors(save.failure, ["text"]);
  const valid = values.text !== "";
  const submit = useSubmit(() => save.save(values), !valid);

  return (
    <AppModal
      footer={
        <>
          <Button variant="light" onPress={onClose}>
            Отмена
          </Button>
          <LoadingButton color="primary" isDisabled={!valid} isLoading={save.pending} onPress={() => submit()}>
            Сохранить
          </LoadingButton>
        </>
      }
      isOpen
      title="Заметка"
      onClose={onClose}
    >
      <form className="space-y-4" onSubmit={submit}>
        <Textarea
          autoFocus
          description={`Осталось ${charsLeft(text, NOTE_TEXT_MAX)} из ${NOTE_TEXT_MAX} знаков`}
          label="Текст"
          maxLength={NOTE_TEXT_MAX}
          minRows={4}
          value={text}
          {...fe.field("text", setText)}
        />
        <LinkPickers value={links} onChange={setLinks} />
        {fe.message && (
          <p className="text-sm text-danger" role="alert">
            {fe.message}
          </p>
        )}
      </form>
      <ConflictDialog save={save} />
    </AppModal>
  );
}

function NoteItem({ note }: { note: Note }) {
  const refresh = useRefreshNotes();
  const [editing, setEditing] = useState(false);
  const [asking, setAsking] = useState(false);
  const remove = useMutation({
    mutationFn: () => api(`/api/v1/notes/${note.id}`, { method: "DELETE" }),
    onSuccess: () => {
      void refresh();
      setAsking(false);
      notify("Заметка удалена");
    },
    onError: notifyError,
  });

  return (
    <li className="rounded-xl border border-divider p-3.5">
      <p className="line-clamp-6 whitespace-pre-wrap break-words text-sm">{note.text}</p>
      <LinkChips note={note} />
      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="text-xs text-default-500">{formatDateTime(note.created_at)}</span>
        <div className="flex gap-1">
          <Button isIconOnly aria-label="Изменить заметку" size="sm" variant="light" onPress={() => setEditing(true)}>
            <Icon name="edit" size={16} />
          </Button>
          <Button isIconOnly aria-label="Удалить заметку" size="sm" variant="light" onPress={() => setAsking(true)}>
            <Icon name="trash" size={16} />
          </Button>
        </div>
      </div>
      {editing && <EditNoteModal note={note} onClose={() => setEditing(false)} />}
      <ConfirmModal confirmLabel="Удалить" danger isLoading={remove.isPending} isOpen={asking} title="Удалить заметку?" onClose={() => setAsking(false)} onConfirm={() => remove.mutate()}>
        Заметка исчезнет насовсем.
      </ConfirmModal>
    </li>
  );
}

function NotesSkeleton({ count }: { count: number }) {
  return (
    <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }, (_, i) => (
        <Bone key={i} className="h-[6.5rem] w-full rounded-xl" />
      ))}
    </div>
  );
}

/** «Все заметки»: a search over every note, newest first. */
function AllNotesModal({ onClose }: { onClose: () => void }) {
  const [q, setQ] = useState("");
  const notes = useNotes({ q: q.trim() || undefined, limit: 200 });

  return (
    <AppModal footer={<Button onPress={onClose}>Закрыть</Button>} guard={false} isOpen size="2xl" title="Все заметки" onClose={onClose}>
      <Input
        isClearable
        aria-label="Поиск по заметкам"
        placeholder="Поиск по тексту"
        startContent={<Icon name="search" size={16} />}
        value={q}
        onClear={() => setQ("")}
        onValueChange={setQ}
      />
      <div className="mt-3 min-h-40">
        <QueryState
          empty={<EmptyState title={q ? "Ничего не найдено" : "Заметок пока нет"} />}
          errorText="Не удалось загрузить заметки"
          isEmpty={(d) => d.items.length === 0}
          query={notes}
          skeleton={<NotesSkeleton count={3} />}
        >
          {(d) => (
            <ul className="grid gap-3 md:grid-cols-2">
              {d.items.map((n) => (
                <NoteItem key={n.id} note={n} />
              ))}
            </ul>
          )}
        </QueryState>
      </div>
    </AppModal>
  );
}

/** «Мои заметки — видны только вам»: quick add (Ctrl/Cmd + Enter), the last six, a link to all of them. */
export function NotesCard() {
  const refresh = useRefreshNotes();
  const notes = useNotes({ limit: 6 });
  const [text, setText] = useState("");
  const [links, setLinks] = useState<Links>(NO_LINKS);
  const [linking, setLinking] = useState(false);
  const [all, setAll] = useState(false);
  const valid = text.trim() !== "";

  const add = useMutation({
    mutationFn: () => api<Note>("/api/v1/notes", { method: "POST", body: { text: text.trim(), ...links } }),
    onSuccess: () => {
      void refresh();
      setText("");
      setLinks(NO_LINKS);
      setLinking(false);
      notify("Заметка добавлена");
    },
  });
  const fe = useFieldErrors(add.error, ["text"]);
  const submit = useSubmit(() => add.mutateAsync(), !valid);
  const linked = Object.values(links).some(Boolean);

  return (
    <section aria-label="Мои заметки" className="min-w-0 rounded-2xl bg-content1 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-medium">
          Мои заметки <span className="font-normal text-default-500">— видны только вам</span>
        </h2>
        <Button size="sm" variant="light" onPress={() => setAll(true)}>
          Все заметки
        </Button>
      </div>
      <form className="mb-4 space-y-3" onSubmit={submit}>
        <Textarea
          aria-label="Новая заметка"
          description={valid ? `Ctrl/⌘ + Enter — сохранить · осталось ${charsLeft(text, NOTE_TEXT_MAX)}` : "Ctrl/⌘ + Enter — сохранить"}
          maxLength={NOTE_TEXT_MAX}
          minRows={2}
          placeholder="Мысль, договорённость, идея…"
          value={text}
          onKeyDown={(e) => {
            if (isSaveShortcut(e)) submit();
          }}
          {...fe.field("text", setText)}
        />
        {linking && <LinkPickers value={links} onChange={setLinks} />}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Button size="sm" startContent={<Icon name="plus" size={14} />} variant="flat" onPress={() => setLinking((l) => !l)}>
            {linking ? "Скрыть привязку" : linked ? "Изменить привязку" : "Привязать к цели, курсу, потоку"}
          </Button>
          <LoadingButton color="primary" isDisabled={!valid} isLoading={add.isPending} size="sm" type="submit">
            Добавить
          </LoadingButton>
        </div>
        {fe.message && (
          <p className="text-sm text-danger" role="alert">
            {fe.message}
          </p>
        )}
      </form>
      <QueryState
        empty={<EmptyState title="Заметок пока нет" hint="Записывайте сюда то, что не должно потеряться." />}
        errorText="Не удалось загрузить заметки"
        isEmpty={(d) => d.items.length === 0}
        query={notes}
        skeleton={<NotesSkeleton count={3} />}
      >
        {(d) => (
          <ul className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {d.items.map((n) => (
              <NoteItem key={n.id} note={n} />
            ))}
          </ul>
        )}
      </QueryState>
      {all && <AllNotesModal onClose={() => setAll(false)} />}
    </section>
  );
}
