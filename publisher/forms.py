from django import forms
from django.forms import inlineformset_factory

from catalog.models import (
    Video, VideoLanguage,
    VideoCluster, VideoClusterLanguage, VideoClusterVideo,
    VideoTriggerMap
)


class VideoForm(forms.ModelForm):
    class Meta:
        model = Video
        fields = [
            "code", "description", "primary_trigger", "primary_therapy",
            "duration_seconds", "thumbnail_url", "is_published", "search_keywords"
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "search_keywords": forms.Textarea(attrs={"rows": 2}),
        }


class VideoLanguageForm(forms.ModelForm):
    class Meta:
        model = VideoLanguage
        fields = ["language_code", "title", "youtube_url"]
        widgets = {
            "title": forms.TextInput(attrs={"style": "width: 100%;"}),
            "youtube_url": forms.TextInput(attrs={"style": "width: 100%;"}),
        }
        help_texts = {
            "youtube_url": "Paste any YouTube URL (watch/embed/youtu.be). The patient page will embed it automatically.",
        }


class VideoClusterForm(forms.ModelForm):
    class Meta:
        model = VideoCluster
        fields = ["code", "trigger", "description", "sort_order", "is_published", "search_keywords"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "search_keywords": forms.Textarea(attrs={"rows": 2}),
        }


class VideoClusterLanguageForm(forms.ModelForm):
    class Meta:
        model = VideoClusterLanguage
        fields = ["language_code", "name"]
        widgets = {"name": forms.TextInput(attrs={"style": "width: 100%;"})}


class VideoClusterVideoForm(forms.ModelForm):
    class Meta:
        model = VideoClusterVideo
        fields = ["video", "sort_order"]


class VideoTriggerMapForm(forms.ModelForm):
    class Meta:
        model = VideoTriggerMap
        fields = ["trigger", "video", "is_primary", "sort_order"]


def make_video_language_formset(extra: int):
    return inlineformset_factory(
        Video,
        VideoLanguage,
        form=VideoLanguageForm,
        fields=["language_code", "title", "youtube_url"],
        extra=extra,
        can_delete=True,
    )


def make_cluster_language_formset(extra: int):
    return inlineformset_factory(
        VideoCluster,
        VideoClusterLanguage,
        form=VideoClusterLanguageForm,
        fields=["language_code", "name"],
        extra=extra,
        can_delete=True,
    )


def make_cluster_video_formset(extra: int):
    return inlineformset_factory(
        VideoCluster,
        VideoClusterVideo,
        form=VideoClusterVideoForm,
        fields=["video", "sort_order"],
        extra=extra,
        can_delete=True,
    )
