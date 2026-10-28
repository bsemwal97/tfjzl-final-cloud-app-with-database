import logging

from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponseRedirect
from django.contrib.auth.models import User
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.views import generic
from django.views.decorators.http import require_POST

# <HINT> Import any new Models here
from .models import Course, Enrollment, Question, Choice, Submission


# Get an instance of a logger
logger = logging.getLogger(__name__)

# Create your views here.


def registration_request(request):
    context = {}

    if request.method == 'POST':
        # Check if user exists
        username = request.POST['username']
        password = request.POST['psw']
        first_name = request.POST['firstname']
        last_name = request.POST['lastname']

        user_exist = User.objects.filter(username=username).exists()

        if not user_exist:
            user = User.objects.create_user(
                username=username,
                first_name=first_name,
                last_name=last_name,
                password=password,
            )
            login(request, user)
            return redirect('onlinecourse:index')

        context['message'] = "User already exists."

    return render(
        request,
        'onlinecourse/user_registration_bootstrap.html',
        context,
    )


def login_request(request):
    context = {}

    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['psw']

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')

        context['message'] = "Invalid username or password."

    return render(
        request,
        'onlinecourse/user_login_bootstrap.html',
        context,
    )


def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


def check_if_enrolled(user, course):
    # Check if user enrolled
    if user.is_authenticated:
        return Enrollment.objects.filter(
            user=user,
            course=course,
        ).exists()

    return False


# CourseListView
class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        user = self.request.user
        courses = Course.objects.order_by('-total_enrollment')[:10]

        for course in courses:
            course.is_enrolled = check_if_enrolled(user, course)

        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_detail_bootstrap.html'


def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    is_enrolled = check_if_enrolled(user, course)

    if not is_enrolled and user.is_authenticated:
        # Create an enrollment
        Enrollment.objects.create(
            user=user,
            course=course,
            mode='honor',
        )

        course.total_enrollment += 1
        course.save()

    return HttpResponseRedirect(
        reverse(
            viewname='onlinecourse:course_details',
            args=(course.id,),
        )
    )


# <HINT> Create a submit view to create an exam submission record for a course enrollment,
# you may implement it based on following logic:
# Get user and course object, then get the associated enrollment object created when the user enrolled the course
# Create a submission object referring to the enrollment
# Collect the selected choices from exam form
# Add each selected choice object to the submission object
# Redirect to show_exam_result with the submission id
#def submit(request, course_id):

@login_required(login_url='onlinecourse:login')
@require_POST
def submit(request, course_id):
    # Get user and course object, then get the associated enrollment
    course = get_object_or_404(Course, pk=course_id)

    enrollment = get_object_or_404(
        Enrollment,
        user=request.user,
        course=course,
    )

    # Create a submission object referring to the enrollment
    submission = Submission.objects.create(
        enrollment=enrollment,
    )

    # Collect the selected choices from exam form
    selected_ids = extract_answers(request)

    selected_choices = Choice.objects.filter(
        id__in=selected_ids,
        question__course=course,
    )

    # Add each selected choice object to the submission object
    submission.choices.add(*selected_choices)

    # Redirect to show_exam_result with the submission id
    return redirect(
        'onlinecourse:exam_result',
        course_id=course.id,
        submission_id=submission.id,
    )


# An example method to collect the selected choices from the exam form from the request object
def extract_answers(request):
    submitted_answers = []

    for key, value in request.POST.items():
        if key.startswith('choice_') and value.isdecimal():
            submitted_answers.append(int(value))

    return submitted_answers


# <HINT> Create an exam result view to check if learner passed exam and show their question results and result for each question,
# you may implement it based on the following logic:
# Get course and submission based on their ids
# Get the selected choice ids from the submission record
# For each selected choice, check if it is a correct answer or not
# Calculate the total score
#def show_exam_result(request, course_id, submission_id):

@login_required(login_url='onlinecourse:login')
def show_exam_result(request, course_id, submission_id):
    # Get course and submission based on their ids
    course = get_object_or_404(Course, pk=course_id)

    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__course=course,
        enrollment__user=request.user,
    )

    # Get the selected choice ids from the submission record
    choices = submission.choices.all()
    selected_ids = list(choices.values_list('id', flat=True))

    questions = course.question_set.prefetch_related('choice_set')

    total_score = 0
    earned_score = 0
    question_results = []

    # For each selected choice, check if it is a correct answer or not
    # Evaluate all selected choices together for each question.
    for question in questions:
        total_score += question.grade
        is_correct = question.is_get_score(selected_ids)

        if is_correct:
            earned_score += question.grade

        question_results.append({
            'question': question,
            'is_correct': is_correct,
        })

    # Calculate the total score as a percentage
    grade = (
        round(earned_score / total_score * 100, 2)
        if total_score > 0
        else 0
    )

    context = {
        'course': course,
        'submission': submission,
        'choices': choices,
        'selected_ids': selected_ids,
        'grade': grade,
        'earned_score': earned_score,
        'total_score': total_score,
        'question_results': question_results,
        'passed': total_score > 0 and grade >= 80,
    }

    return render(
        request,
        'onlinecourse/exam_result_bootstrap.html',
        context,
    )