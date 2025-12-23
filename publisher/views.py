from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from catalog.models import TherapyArea, VideoCluster, Video, VideoLanguage, Trigger, TriggerCluster
from .forms import (
    TherapyAreaForm,
    VideoClusterForm,
    VideoForm,
    make_video_language_formset,
    TriggerForm,
    TriggerClusterForm,
)


@login_required
def dashboard(request):
    return render(request, "publisher/dashboard.html")


# -------------------------------
# Therapy Areas CRUD
# -------------------------------
@staff_member_required
def therapy_list(request):
    q = request.GET.get("q", "").strip()
    qs = (
        TherapyArea.objects.filter(is_active=True)
        .exclude(code__istartswith="TEST")
        .exclude(display_name__istartswith="Test")
        .order_by("sort_order", "code")
    )
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(display_name__icontains=q))
    return render(request, "publisher/therapy_list.html", {"rows": qs, "q": q})


@staff_member_required
def therapy_create(request):
    if request.method == "POST":
        form = TherapyAreaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Therapy area created.")
            return redirect("publisher:therapy_list")
    else:
        form = TherapyAreaForm()
    return render(request, "publisher/therapy_form.html", {"form": form, "page_title": "Add Therapy Area"})


@staff_member_required
def therapy_edit(request, pk):
    obj = get_object_or_404(TherapyArea, pk=pk)
    if request.method == "POST":
        form = TherapyAreaForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Therapy area updated.")
            return redirect("publisher:therapy_list")
    else:
        form = TherapyAreaForm(instance=obj)
    return render(request, "publisher/therapy_form.html", {"form": form, "page_title": "Edit Therapy Area"})


@staff_member_required
def therapy_delete(request, pk):
    obj = get_object_or_404(TherapyArea, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Therapy area deleted.")
        return redirect("publisher:therapy_list")
    return render(
        request, "publisher/confirm_delete.html", {"object": obj, "cancel_url": "publisher:therapy_list"}
    )


# -------------------------------
# Video Clusters CRUD
# -------------------------------
@staff_member_required
def cluster_list(request):
    q = request.GET.get("q", "").strip()
    qs = VideoCluster.objects.all().order_by("sort_order", "code")
    if q:
        qs = qs.filter(code__icontains=q) | qs.filter(display_name__icontains=q)
    return render(request, "publisher/cluster_list.html", {"rows": qs, "q": q})


@staff_member_required
def cluster_create(request):
    if request.method == "POST":
        form = VideoClusterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Cluster created.")
            return redirect("publisher:cluster_list")
    else:
        form = VideoClusterForm()
    return render(request, "publisher/cluster_form.html", {"form": form, "page_title": "Add Cluster"})


@staff_member_required
def cluster_edit(request, pk):
    obj = get_object_or_404(VideoCluster, pk=pk)
    if request.method == "POST":
        form = VideoClusterForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Cluster updated.")
            return redirect("publisher:cluster_list")
    else:
        form = VideoClusterForm(instance=obj)
    return render(request, "publisher/cluster_form.html", {"form": form, "page_title": "Edit Cluster"})


@staff_member_required
def cluster_delete(request, pk):
    obj = get_object_or_404(VideoCluster, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Cluster deleted.")
        return redirect("publisher:cluster_list")
    return render(
        request, "publisher/confirm_delete.html", {"object": obj, "cancel_url": "publisher:cluster_list"}
    )


# -------------------------------
# Videos CRUD
# -------------------------------
@staff_member_required
def video_list(request):
    q = request.GET.get("q", "").strip()
    qs = Video.objects.all().order_by("sort_order", "code")
    if q:
        qs = qs.filter(code__icontains=q)
    return render(request, "publisher/video_list.html", {"rows": qs, "q": q})


@staff_member_required
def video_create(request):
    FormSet = make_video_language_formset(extra=8)
    if request.method == "POST":
        form = VideoForm(request.POST)
        formset = FormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                video = form.save()
                formset.instance = video
                formset.save()
            messages.success(request, "Video created.")
            return redirect("publisher:video_list")
    else:
        form = VideoForm()
        initial = [{"language_code": code} for code in ["en", "hi", "te", "ml", "mr", "kn", "ta", "bn"]]
        formset = FormSet(initial=initial)

    return render(
        request,
        "publisher/video_form.html",
        {"form": form, "formset": formset, "page_title": "Add Video"},
    )


@staff_member_required
def video_edit(request, pk):
    video = get_object_or_404(Video, pk=pk)
    existing = {vl.language_code: vl for vl in VideoLanguage.objects.filter(video=video)}
    missing = [code for code in ["en", "hi", "te", "ml", "mr", "kn", "ta", "bn"] if code not in existing]

    FormSet = make_video_language_formset(extra=len(missing))

    if request.method == "POST":
        form = VideoForm(request.POST, instance=video)
        formset = FormSet(request.POST, instance=video)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
            messages.success(request, "Video updated.")
            return redirect("publisher:video_list")
    else:
        form = VideoForm(instance=video)
        initial = [{"language_code": code} for code in missing]
        formset = FormSet(instance=video, initial=initial)

    return render(
        request, "publisher/video_form.html", {"form": form, "formset": formset, "page_title": "Edit Video"}
    )


@staff_member_required
def video_delete(request, pk):
    obj = get_object_or_404(Video, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Video deleted.")
        return redirect("publisher:video_list")
    return render(request, "publisher/confirm_delete.html", {"object": obj, "cancel_url": "publisher:video_list"})


# -------------------------------
# Triggers CRUD
# -------------------------------
@staff_member_required
def trigger_list(request):
    q = request.GET.get("q", "").strip()
    qs = Trigger.objects.select_related("primary_therapy").all().order_by("sort_order", "display_name")
    if q:
        qs = qs.filter(display_name__icontains=q)
    return render(request, "publisher/trigger_list.html", {"rows": qs, "q": q})


@staff_member_required
def trigger_create(request):
    if request.method == "POST":
        form = TriggerForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Trigger created.")
            return redirect("publisher:trigger_list")
    else:
        form = TriggerForm()
    return render(request, "publisher/trigger_form.html", {"form": form, "page_title": "Add Trigger"})


@staff_member_required
def trigger_edit(request, pk):
    obj = get_object_or_404(Trigger, pk=pk)
    if request.method == "POST":
        form = TriggerForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Trigger updated.")
            return redirect("publisher:trigger_list")
    else:
        form = TriggerForm(instance=obj)
    return render(request, "publisher/trigger_form.html", {"form": form, "page_title": "Edit Trigger"})


@staff_member_required
def trigger_delete(request, pk):
    obj = get_object_or_404(Trigger, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Trigger deleted.")
        return redirect("publisher:trigger_list")
    return render(request, "publisher/confirm_delete.html", {"object": obj, "cancel_url": "publisher:trigger_list"})


# -------------------------------
# Trigger Clusters CRUD
# -------------------------------
@staff_member_required
def trigger_cluster_list(request):
    q = request.GET.get("q", "").strip()
    qs = TriggerCluster.objects.all().order_by("sort_order", "display_name")
    if q:
        qs = qs.filter(display_name__icontains=q)
    return render(request, "publisher/trigger_cluster_list.html", {"rows": qs, "q": q})


@staff_member_required
def trigger_cluster_create(request):
    if request.method == "POST":
        form = TriggerClusterForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Trigger cluster created.")
            return redirect("publisher:trigger_cluster_list")
    else:
        form = TriggerClusterForm()
    return render(request, "publisher/trigger_cluster_form.html", {"form": form, "page_title": "Add Trigger Cluster"})


@staff_member_required
def trigger_cluster_edit(request, pk):
    obj = get_object_or_404(TriggerCluster, pk=pk)
    if request.method == "POST":
        form = TriggerClusterForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Trigger cluster updated.")
            return redirect("publisher:trigger_cluster_list")
    else:
        form = TriggerClusterForm(instance=obj)
    return render(request, "publisher/trigger_cluster_form.html", {"form": form, "page_title": "Edit Trigger Cluster"})


@staff_member_required
def trigger_cluster_delete(request, pk):
    obj = get_object_or_404(TriggerCluster, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Trigger cluster deleted.")
        return redirect("publisher:trigger_cluster_list")
    return render(
        request, "publisher/confirm_delete.html", {"object": obj, "cancel_url": "publisher:trigger_cluster_list"}
    )


# -------------------------------
# Trigger Maps CRUD (stubs to avoid errors)
# -------------------------------
@staff_member_required
def map_list(request):
    return render(request, "publisher/map_list.html")


@staff_member_required
def map_create(request):
    return render(request, "publisher/map_form.html")


@staff_member_required
def map_edit(request, pk):
    return render(request, "publisher/map_form.html")
